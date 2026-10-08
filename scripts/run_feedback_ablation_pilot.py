"""BigCodeBench feedback-content pilot: scalar outcome versus sanitized execution evidence.

Arm A is F's completed SkillOpt stage 1 (v7, scalar feedback); it is reused, not
rerun. Arm B repeats that learning manifest field for field except
``feedback_profile`` (sanitized development execution evidence: a fixed-vocabulary
exception class, the failure locus and the candidate's own failing line; no
hidden test text, messages or values). Arm B's selected Skill is evaluated on the
same BCB panel through the same verified derived evaluation source. One history
per arm on previously exposed development data: a direction-finding pilot, not a
significance or independent-final claim, and not a Research/Rubric verifier result.
"""
from __future__ import annotations

import argparse
import difflib
import fcntl
import hashlib
import json
from pathlib import Path

import skillopt
from scripts import continue_fivebench_baselines as sequence
from scripts.report_fivebench_generalization import aggregate, paired, row_index
from skillopt.coevolution_v5.core import seal
from skillopt.continual_eval.core import read_json, require, safe_path, write_json
from skillopt.continual_learning.contracts import manifest, validate_manifest
from skillopt.continual_learning.execution_evidence import PROFILE, sanitize
from skillopt.continual_learning.feedback import PROFILE as SCALAR
from skillopt.continual_learning.skillopt import native_sources
from skillopt.validator_pilot.api import digest

VERSION = "bcb-feedback-ablation-pilot-v2"
BENCHMARK = "bigcodebench"
STAGE = "skillopt/s1-bigcodebench"
# The only learning sources allowed to differ from arm A's frozen tree; the exact
# diff is stored for review and the resulting hashes are pinned.
ALLOWED_SOURCE_CHANGES = {"continual_learning/contracts.py", "continual_learning/feedback.py",
                          "continual_learning/skillopt.py", "continual_learning/execution_evidence.py"}
# Reviewed post-change hashes of exactly those files; any other version is refused.
REVIEWED_SOURCES = {
    "continual_learning/contracts.py": "66cf7c9d593a4deebaa7df66eeb7a990d4538bd2488ab91f62b73ee5c75b4063",
    "continual_learning/execution_evidence.py": "d2d21516e5035bf904b7346cb84170fc085d7223aa0a84c9a34321f7b7526660",
    "continual_learning/feedback.py": "882e07b2c9fa1dfebcf82fc9a2f54cb49946fc842c5dc438b1ce0533fc159421",
    "continual_learning/skillopt.py": "978c0189888b8b3833b0fad2104a4daaeccdf7af8477f9169327bd8b56a0656f",
}


def _sha(path):
    return hashlib.sha256(safe_path(path).read_bytes()).hexdigest()


def _budget(value):
    return value["recovery_policy"]["skill_budget_bytes"]


def _arm_a(f_root, f_protocol, verify_into=None):
    """F's completed scalar stage 1, with every manifest/learning/Skill binding checked."""
    arm_a = read_json(f_root / STAGE / "manifest.json", sealed=True)
    require(arm_a["version"] == f_protocol["learning_version"] and arm_a["feedback_profile"] == SCALAR
            and arm_a["method"] == "skillopt" and arm_a["benchmark"] == BENCHMARK,
            "Arm A must be F's scalar-feedback SkillOpt learning manifest")
    stage = read_json(f_root / STAGE / "stage.json", sealed=True)
    learning = read_json(f_root / STAGE / "learning/result.json", sealed=True)
    require(learning["status"] == "completed" and stage["learning_completed"] is True
            and stage["action"] in {"selected_update", "completed_no_update"}, "Arm A learning did not complete")
    require(stage["protocol_hash"] == f_protocol["record_hash"] and stage["method"] == "skillopt"
            and stage["stage"] == 1 and stage["benchmark"] == BENCHMARK
            and stage["manifest_hash"] == arm_a["record_hash"]
            and stage["learning_result_hash"] == learning["record_hash"]
            and sequence.transition("", learning, _budget(arm_a))["skill"] == stage["skill"],
            "Arm A stage, learning result and Skill do not bind")
    identity = _verify_learning(f_root / STAGE / "learning", arm_a, learning)
    reference, cell = f_protocol["references"][BENCHMARK], stage["cells"][BENCHMARK]
    if stage["skill"]:
        request = read_json(cell["request_path"], sealed=True)
        require(cell["kind"] == "new_frozen_policy_evaluation" and cell["source_stage"] == 1
                and read_json(cell["output_path"], sealed=True) == cell["result"]
                and request["chain"] == [stage["skill"]] and request["benchmark"] == BENCHMARK
                and request["reference"] == sequence._reference_identity(reference)
                and request["baseline_plan_hash"] == reference["plan_hash"], "Arm A evaluation does not bind")
        if verify_into is not None:
            # Recompute checkpoints, configuration and scores in place; never resample.
            verified = sequence._invoke(reference, "verify-evaluation", cell["request_path"], verify_into,
                                        log=verify_into.with_suffix(".log"))
            require(verified == cell["result"], "Arm A evaluation does not reproduce")
    else:
        require(cell["kind"] == "historical_empty_policy" and cell["result"] == reference,
                "An empty arm A Skill must reuse the No-Skill observation")
    return arm_a, stage, learning, identity


def _bound_arm_a(root, protocol):
    """Arm A exactly as prepared, its evaluation recomputed by the frozen worker."""
    f_root = safe_path(protocol["f_study"])
    f_protocol = read_json(f_root / "protocol.json", sealed=True)
    require(f_protocol["record_hash"] == protocol["f_protocol_hash"], "F protocol changed")
    # Verification rewrites F's content-addressed report byte-identically; its own
    # output lives in the pilot directory.
    arm_a, stage, learning, _ = _arm_a(f_root, f_protocol, verify_into=root / "arm-a-verification.json")
    require(stage["record_hash"] == protocol["arm_a"]["stage_hash"]
            and arm_a["record_hash"] == protocol["arm_a"]["manifest_hash"]
            and learning["record_hash"] == protocol["arm_a"]["learning_result_hash"], "Arm A changed since preparation")
    return arm_a, stage, learning


def _verify_learning(root, value, result):
    """result -> identity -> manifest, and every recorded learning artifact hash."""
    identity = read_json(root / "identity.json", sealed=True)
    require(identity["manifest"] == value and result["identity_hash"] == identity["record_hash"],
            "Learning result does not belong to this manifest")
    require(all((root / path).is_file() and _sha(root / path) == digest_ for path, digest_ in result["artifacts"].items()),
            "Learning artifacts are missing or changed")
    return identity


def _evaluation_source(reference, budget):
    """The frozen No-Skill source matches its plan; the derived copy differs only in the budget."""
    plan = read_json(safe_path(reference["root"]) / "plan.json", sealed=True)
    require(plan["record_hash"] == reference["plan_hash"], "No-Skill plan is not the frozen reference plan")
    source = safe_path(reference["source"])
    require(all((source / "skillopt" / name).is_file() and _sha(source / "skillopt" / name) == value
                for name, value in plan["source_identity"].items()), "Frozen evaluation source drifted from its plan")
    return sequence._check_budget_source(reference["source"], reference["evaluation_source"], budget)


def _check_frozen(protocol, arm_b):
    require(native_sources() == protocol["native_sources"], "Native optimizer sources changed")
    require(_evaluation_source(protocol["reference"], _budget(arm_b)) == protocol["evaluation_source_changes"],
            "Derived evaluation source changed")


def prepare(f_study, f_source, output):
    f_root, f_src, root = safe_path(f_study), safe_path(f_source), safe_path(output)
    require(not root.exists(), "A new pilot directory is required")
    f_protocol = read_json(f_root / "protocol.json", sealed=True)
    require(f_protocol["version"] == sequence.BUDGET_SEQUENCE and "skillopt" in f_protocol["methods"],
            "Arm A must come from F's v4 study")
    arm_a, stage, learning, identity = _arm_a(f_root, f_protocol)
    role = f_protocol["roles"][BENCHMARK]
    excluded = sorted(set(arm_a["train_families"]) | set(arm_a["selection_families"]))
    require(excluded == sorted(set(role["train"]) | set(role["selection"])), "Role metadata disagrees with arm A")
    panel = read_json(role["path"])
    arm_b = manifest(panel, train_families=arm_a["train_families"], selection_families=arm_a["selection_families"],
                     model=arm_a["model"], budget=arm_a["budget"], runtime=arm_a["runtime"],
                     parent_skill=arm_a["parent_skill"], seed=arm_a["seed"], method="skillopt",
                     version=arm_a["version"], recovery_policy=arm_a["recovery_policy"], feedback_profile=PROFILE)
    volatile = {"feedback_profile", "record_hash", "source_identity"}
    require({k: v for k, v in arm_a.items() if k not in volatile} == {k: v for k, v in arm_b.items() if k not in volatile},
            "Arm B differs from arm A beyond the feedback profile (including host runtime)")
    before, after = arm_a["source_identity"], arm_b["source_identity"]
    changed = sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))
    require(set(changed) <= ALLOWED_SOURCE_CHANGES and all(after.get(k) == REVIEWED_SOURCES.get(k) for k in changed),
            "Learning sources changed beyond the reviewed evidence wiring")
    require(all((f_src / "skillopt" / k).is_file() and _sha(f_src / "skillopt" / k) == v for k, v in before.items()),
            "--f-source is not arm A's source tree")
    require(native_sources() == identity["native_sources"], "Native optimizer sources differ from arm A")
    package = Path(skillopt.__file__).parent
    patch = []
    for key in changed:
        old = (f_src / "skillopt" / key).read_text().splitlines(True) if key in before else []
        patch += difflib.unified_diff(old, (package / key).read_text().splitlines(True), f"a/{key}", f"b/{key}")
    reference = f_protocol["references"][BENCHMARK]
    evaluation_changes = _evaluation_source(reference, _budget(arm_b))
    root.mkdir(parents=True, mode=0o700)
    write_json(root / "panel.json", panel)
    write_json(root / "manifest-b.json", arm_b)
    (root / "source-diff.patch").write_text("".join(patch))
    protocol = seal({"version": VERSION, "f_protocol_hash": f_protocol["record_hash"], "f_study": str(f_root),
                     "arm_a": {"stage_hash": stage["record_hash"], "manifest_hash": arm_a["record_hash"],
                               "learning_result_hash": learning["record_hash"], "skill_hash": digest(stage["skill"])},
                     "arm_b": {"manifest_hash": arm_b["record_hash"], "feedback_profile": PROFILE},
                     "learning_source_changes": {k: {"before": before.get(k), "after": after.get(k)} for k in changed},
                     "source_diff_sha256": _sha(root / "source-diff.patch"), "native_sources": identity["native_sources"],
                     "evaluation_source_changes": evaluation_changes, "panel_sha256": _sha(root / "panel.json"),
                     "reference": reference, "excluded_families": excluded,
                     "learning_model_service": f_protocol["learning_model_service"],
                     "learning_client_options": f_protocol["learning_client_options"], "model": f_protocol["model"],
                     "native_lock": f_protocol["config"]["native_lock"], "workers": f_protocol["config"]["workers"],
                     "histories_per_arm": 1, "data_scope": "previously_exposed_development_not_final",
                     "claim": "direction_finding_pilot_not_significance", "deployment_authorized": False})
    write_json(root / "protocol.json", protocol)
    return protocol


def _load(output):
    root = safe_path(output)
    protocol = read_json(root / "protocol.json", sealed=True)
    require(protocol["version"] == VERSION and _sha(root / "panel.json") == protocol["panel_sha256"]
            and _sha(root / "source-diff.patch") == protocol["source_diff_sha256"], "Pilot protocol or panel changed")
    panel = read_json(root / "panel.json")
    arm_b = validate_manifest(read_json(root / "manifest-b.json", sealed=True), panel)  # current sources = pinned
    require(arm_b["record_hash"] == protocol["arm_b"]["manifest_hash"], "Arm B manifest changed")
    return root, protocol, panel, arm_b


def _request(root, protocol, skill, repo):
    reference = protocol["reference"]
    return seal({"reference": sequence._reference_identity(reference), "benchmark": BENCHMARK,
                 "baseline_plan_hash": reference["plan_hash"], "baseline_report_hash": reference["report_hash"],
                 "run": str(root / "evaluations" / BENCHMARK), "method": "skillopt", "chain": [skill],
                 "stage_hash": protocol["record_hash"], "repo": str(safe_path(repo)), "workers": protocol["workers"]})


def _bound_result(root, protocol, arm_b):
    """Arm B's result with its sources, learning, Skill and evaluation bindings rechecked."""
    _check_frozen(protocol, arm_b)  # also for an empty Skill, which runs no verifier
    result = read_json(root / "result.json", sealed=True)
    learning = read_json(root / "learning/result.json", sealed=True)
    _verify_learning(root / "learning", arm_b, learning)
    skill = sequence.transition("", learning, _budget(arm_b))["skill"]
    require(result["protocol_hash"] == protocol["record_hash"] and result["learning_result_hash"] == learning["record_hash"]
            and result["skill_hash"] == digest(skill), "Arm B result does not bind to its learning")
    evaluation = None
    if skill:
        evaluation = read_json(root / f"evaluation-{BENCHMARK}.json", sealed=True)
        require(result["evaluation_hash"] == evaluation["record_hash"], "Arm B evaluation was substituted")
        path = root / "requests/evaluate.json"
        require(read_json(path, sealed=True)["chain"] == [skill], "Arm B evaluation request names another Skill")
        # Recompute checkpoints, configuration and scores in place; never resample.
        verified = sequence._invoke(protocol["reference"], "verify-evaluation", path,
                                    root / f"evaluation-{BENCHMARK}.json", log=root / "evaluation.log")
        require(verified == evaluation, "Arm B evaluation does not reproduce")
    else:
        require(result["evaluation_hash"] is None, "An empty Skill must reuse the No-Skill observation")
    return result, learning, skill, evaluation


def run(output, repo):
    from skillopt.continual_learning.skillopt import run_stage

    root, protocol, panel, arm_b = _load(output)
    _check_frozen(protocol, arm_b)
    if (root / "result.json").exists():
        return _bound_result(root, protocol, arm_b)[0]
    service, reference = protocol["learning_model_service"], protocol["reference"]
    with safe_path(protocol["native_lock"]).open("a") as resource:
        # The same host-wide lock as F: never overlap native scorers with it.
        fcntl.flock(resource.fileno(), fcntl.LOCK_EX)
        _, protocol, panel, arm_b = _load(output)  # recheck sources after the wait
        _check_frozen(protocol, arm_b)
        _bound_arm_a(root, protocol)  # before any paid learning
        sequence.check_client_service(repo, protocol["model"], root / "client-check", service,
                                      client_options=protocol["learning_client_options"])
        learning = run_stage(arm_b, panel, root / "learning", repo=repo)
        sequence.require_safe_handoff(root / "learning", learning)
        sequence.verify_service(root / "learning", service)
        skill = sequence.transition("", learning, _budget(arm_b))["skill"]
        evaluation = None
        if skill:
            path, expected = root / "requests/evaluate.json", _request(root, protocol, skill, repo)
            if path.exists():
                require(read_json(path, sealed=True) == expected, "Existing evaluation request is stale")
            else:
                write_json(path, expected)
            target = root / f"evaluation-{BENCHMARK}.json"
            # A completed evaluation is verified in place; a begun one is never resampled.
            operation = "verify-evaluation" if target.exists() else "evaluate"
            evaluation = sequence._invoke(reference, operation, path, target, log=root / "evaluation.log")
    result = seal({"protocol_hash": protocol["record_hash"], "learning_result_hash": learning["record_hash"],
                   "learning_status": learning["status"], "learning_reason": learning["reason"],
                   "skill_hash": digest(skill), "skill_bytes": len(skill.encode()),
                   "evaluation_hash": evaluation["record_hash"] if evaluation else None,
                   "evaluation_reused_no_skill": not skill})
    write_json(root / "result.json", result)
    return result


def _evidence_coverage(root, arm_b, learning):
    """Only hash-verified, recorded executions authorized by arm B's manifest."""
    loci, failed, available = {}, 0, 0
    for name in sorted(p for p in learning["artifacts"] if p.startswith("evaluations/")):
        row = read_json(root / "learning" / name, sealed=True)
        require(row["request"]["manifest_hash"] == arm_b["record_hash"], "Execution not authorized by arm B")
        if row["request"]["role"] != "train" or row["score"]["status"] != "fail":
            continue
        failed += 1
        evidence = sanitize(row["prediction"]["output"], (row["score"].get("metrics") or {}).get("details"))
        available += evidence["status"] == "available"
        for case in evidence["cases"]:
            loci[case["locus"]] = loci.get(case["locus"], 0) + 1
    return {"failed_train_executions": failed, "with_evidence": available, "loci": dict(sorted(loci.items()))}


def _learning_view(value):
    return {"status": value["status"], "reason": value["reason"],
            "initial_selection_score": value.get("initial_selection_score"), "selected_score": value.get("selected_score"),
            "steps": [{k: s.get(k) for k in ("step", "gate_action", "parent_score", "candidate_score",
                                             "jointly_known", "candidate_new_unknown")} for s in value["steps"]],
            "costs": {k: value["costs"].get(k) for k in ("logical_calls", "http_attempts",
                                                         "reported_tokens_known_subtotal", "missing_usage_calls")}}


def report(output):
    root, protocol, _, arm_b = _load(output)
    result, learning_b, skill_b, evaluation = _bound_result(root, protocol, arm_b)
    _, stage, learning_a = _bound_arm_a(root, protocol)
    reference = protocol["reference"]
    base = row_index(reference["rows"])
    a_rows = stage["cells"][BENCHMARK]["result"]["rows"]
    b_rows = evaluation["rows"] if evaluation else list(reference["rows"])
    excluded = set(protocol["excluded_families"])

    def held(rows):
        return [r for r in rows if r["family_id"] not in excluded]

    comparisons = {}
    for name, rows, against in (("a_vs_no_skill", a_rows, base), ("b_vs_no_skill", b_rows, base),
                                ("b_vs_a", b_rows, row_index(a_rows))):
        held_against = {k: r for k, r in against.items() if r["family_id"] not in excluded}
        comparisons[name] = {"all": paired(rows, against), "learning_family_excluded": paired(held(rows), held_against)}
    return seal({"version": VERSION + "-report", "protocol_hash": protocol["record_hash"],
                 "arms": {"a_scalar_reused_f_stage1": {"skill_hash": digest(stage["skill"]),
                                                       "skill_bytes": len(stage["skill"].encode()),
                                                       "learning": _learning_view(learning_a),
                                                       "evaluation": aggregate(a_rows, base)},
                          "b_execution_evidence": {"skill_hash": result["skill_hash"], "skill_bytes": len(skill_b.encode()),
                                                   "learning": _learning_view(learning_b),
                                                   "evaluation": aggregate(b_rows, base),
                                                   "evaluation_reused_no_skill": result["evaluation_reused_no_skill"],
                                                   "evidence_coverage": _evidence_coverage(root, arm_b, learning_b)}},
                 "comparisons": comparisons, "learning_family_excluded_positions":
                 sum(1 for r in base.values() if r["family_id"] not in excluded),
                 "histories_per_arm": 1, "claim": protocol["claim"], "data_scope": protocol["data_scope"],
                 "significance_claimed": False, "deployment_authorized": False})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "run", "report"))
    parser.add_argument("--output", required=True, help="Pilot directory (new for prepare)")
    parser.add_argument("--f-study")
    parser.add_argument("--f-source", help="Arm A's frozen source tree (verified against its manifest)")
    parser.add_argument("--repo")
    parser.add_argument("--export", help="New report directory outside the pilot")
    args = parser.parse_args()
    if args.command == "prepare":
        require(args.f_study is not None and args.f_source is not None, "--f-study and --f-source required")
        print(json.dumps({"protocol_hash": prepare(args.f_study, args.f_source, args.output)["record_hash"]}))
    elif args.command == "run":
        require(args.repo is not None, "--repo required")
        print(json.dumps(run(args.output, args.repo)))
    else:
        require(args.export is not None, "--export required")
        export, pilot = safe_path(args.export), safe_path(args.output)
        inside = any(p.exists() and p.samefile(pilot) for p in (export, *export.parents))
        require(not export.exists() and not inside, "Use a new export outside the pilot")
        value = report(args.output)
        export.mkdir(parents=True, mode=0o700)
        write_json(export / "report.json", value)
        print(json.dumps({"record_hash": value["record_hash"]}))


if __name__ == "__main__":
    main()
