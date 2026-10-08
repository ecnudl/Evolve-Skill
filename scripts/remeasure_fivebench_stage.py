"""Re-measure the unchanged policy of a frozen five-domain stage (paid; user request 10/4).

A stage that ended Pending, or completed without an update, keeps its parent's
Skill, so the sequential orchestrator reuses the parent's five-domain observation
instead of sampling again. On the user's request this draws one new, independent
five-domain evaluation of exactly that stage's policy -- the same Skill chain,
request shape, budget-derived evaluation source, frozen worker, model service,
scorer runtime overrides and worker count as the study -- into a new directory.
The study is never written: only its read-only frozen-file check runs, never
``check()``, which re-inspects references into the study. ``run`` waits on the
study's native lock, so it cannot overlap the running study, and never resumes a
begun evaluation automatically. The result is a re-measurement of an unchanged
Skill, reported next to the study's reused cell; it never replaces that cell. An
empty Skill re-measures the No-Skill policy: the solver prompt only gains guidance
for a non-empty Skill, so the model sees exactly the No-Skill prompt.

Run with PYTHONPATH (and cwd) at the study's own frozen orchestrator source, so the
frozen-file check and the evaluation worker are exactly the study's.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
from contextlib import ExitStack

from scripts import continue_fivebench_baselines as sequence
from scripts.report_fivebench_generalization import aggregate, paired, row_index
from skillopt.coevolution_v5.core import seal
from skillopt.continual_eval.core import checkpoint_path, output_lock, read_json, require, safe_path, write_json

VERSION = "fivebench-stage-remeasure-v3"


def _study(study):
    root = safe_path(study)
    protocol = read_json(root / "protocol.json", sealed=True)
    require(protocol["root"] == str(root)
            and protocol["version"] in {sequence.VERSION, *sequence.RECOVERY_SEQUENCES}, "Protocol binding mismatch")
    sequence.check_frozen_files(protocol)  # read-only, unlike sequence.check()
    return root, protocol


def _outside(out, root, protocol):
    """The output may not overlap the study, any frozen reference run, or any frozen source."""
    frozen = {root} | {safe_path(ref[k]) for ref in protocol["references"].values()
                       for k in ("root", "source", "evaluation_source") if k in ref}
    require(all(not out.is_relative_to(path) and not path.is_relative_to(out) for path in frozen),
            "Use a new directory outside the study and its frozen references")


def _stages(root, protocol, method, number):
    """Sealed stage records 1..number, bound exactly as the orchestrator binds its chain."""
    require(method in protocol["methods"] and type(number) is int and 1 <= number <= len(protocol["order"]),
            "Unsupported method or stage")
    previous, parent_hash, stages = "", None, []
    for stage_number, benchmark in enumerate(protocol["order"][:number], 1):
        stage = read_json(root / method / f"s{stage_number}-{benchmark}" / "stage.json", sealed=True)
        require(stage["protocol_hash"] == protocol["record_hash"] and stage["method"] == method
                and stage["stage"] == stage_number and stage["benchmark"] == benchmark
                and stage["parent_skill"] == previous and stage["parent_stage_hash"] == parent_hash,
                "Stage chain binding mismatch")
        stages.append(stage)
        previous, parent_hash = stage["skill"], stage["record_hash"]
    return stages


def _request(protocol, target, run, method, chain, stage_hash, repo):
    """The orchestrator's own evaluation request for this policy, with a new run directory."""
    ref = protocol["references"][target]
    return seal({"reference": sequence._reference_identity(ref), "benchmark": target,
                 "baseline_plan_hash": ref["plan_hash"], "baseline_report_hash": ref["report_hash"],
                 "run": str(run), "method": method, "chain": chain, "stage_hash": stage_hash,
                 "repo": str(safe_path(repo)), "workers": protocol["config"]["workers"],
                 **({"evaluation_runtime": protocol["evaluation_runtime_overrides"][target]}
                    if target in protocol.get("evaluation_runtime_overrides", {}) else {})})


def prepare(study, method, number, output, repo):
    root, protocol = _study(study)
    out = safe_path(output)
    _outside(out, root, protocol)
    require(not out.exists(), "Use a new directory outside the study and its frozen references")
    stages = _stages(root, protocol, method, number)
    stage = stages[-1]
    require(all(cell.get("reused") is True for cell in stage["cells"].values()),
            "Only a stage that reused every observation is re-measured")
    chain = [s["skill"] for s in stages]
    out.mkdir(parents=True, mode=0o700)
    requests = {}
    for target in protocol["order"]:
        path = out / f"requests/{target}.json"
        write_json(path, _request(protocol, target, out / f"evaluations/{target}", method, chain,
                                  stage["record_hash"], repo))
        requests[target] = str(path)
    plan = seal({"version": VERSION, "study": str(root), "protocol_hash": protocol["record_hash"],
                 "method": method, "stage": number, "stage_hash": stage["record_hash"],
                 "skill_sha256": hashlib.sha256(stage["skill"].encode()).hexdigest(),
                 "skill_bytes": len(stage["skill"].encode()), "repo": str(safe_path(repo)), "requests": requests,
                 "reason": "user_requested_remeasurement_of_unchanged_stage_policy",
                 "replaces_reused_cells": False})
    write_json(out / "remeasure.json", plan)
    return plan


def candidates(study):
    """Completed stages whose five cells all reuse an earlier observation, in method and stage order."""
    root, protocol = _study(study)
    found = []
    for method in protocol["methods"]:
        for number in range(1, len(protocol["order"]) + 1):
            if not (root / method / f"s{number}-{protocol['order'][number - 1]}" / "stage.json").is_file():
                break
            stage = _stages(root, protocol, method, number)[-1]
            if all(cell.get("reused") is True for cell in stage["cells"].values()):
                found.append((method, number))
    return found


def _load(output):
    out = safe_path(output)
    plan = read_json(out / "remeasure.json", sealed=True)
    require(plan["version"] == VERSION, "Unsupported re-measurement")
    root, protocol = _study(plan["study"])
    _outside(out, root, protocol)
    stages = _stages(root, protocol, plan["method"], plan["stage"])
    require(plan["protocol_hash"] == protocol["record_hash"] and stages[-1]["record_hash"] == plan["stage_hash"],
            "The study or stage changed")
    chain = [s["skill"] for s in stages]
    for target in protocol["order"]:
        expected = _request(protocol, target, out / f"evaluations/{target}", plan["method"], chain,
                            plan["stage_hash"], plan["repo"])
        require(plan["requests"][target] == str(out / f"requests/{target}.json")
                and read_json(plan["requests"][target], sealed=True) == expected, "Re-measurement request changed")
    return out, plan, protocol, stages[-1]


def run(output):
    from skillopt.continual_learning.launch import learning_environment

    out, plan, protocol, stage = _load(output)
    results = {}
    with output_lock(out), safe_path(protocol["config"]["native_lock"]).open("a") as lock, ExitStack() as launch:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)  # waits until the running study releases its native lock
        # Everything may have changed during the wait: re-bind plan, stage and requests before any paid call.
        out, plan, protocol, stage = _load(output)
        launch.enter_context(learning_environment({"benchmark": "alfworld", "model": protocol["model"],
                                                   "runtime": protocol["roles"]["alfworld"]["runtime"]}))
        for target in protocol["order"]:
            ref, request = protocol["references"][target], plan["requests"][target]
            # ... and again for this request immediately before it is handed to the worker.
            require(read_json(request, sealed=True) == _request(
                protocol, target, out / f"evaluations/{target}", plan["method"], [*_skills(plan, protocol)],
                plan["stage_hash"], plan["repo"]), "Re-measurement request changed")
            done = out / f"evaluation-{target}.json"
            if done.exists():
                verified = sequence._invoke(ref, "verify-evaluation", request, out / f"verify-{target}.json",
                                            log=out / f"verify-{target}.log")
                require(verified == read_json(done, sealed=True), "Recorded re-measurement changed")
            else:
                require(not (out / f"evaluations/{target}").exists(),
                        "An interrupted evaluation needs operator review; it is never resumed automatically")
                sequence._invoke(ref, "evaluate", request, done, log=out / f"evaluation-{target}.log")
            # The policy the worker actually evaluated must be this stage's Skill.
            evaluated = read_json(checkpoint_path(out / f"evaluations/{target}", plan["method"], "h0", plan["stage"]),
                                  sealed=True)
            require(evaluated["skill_text"] == stage["skill"], "Evaluated policy differs from the stage policy")
            results[target] = read_json(done, sealed=True)
    summary = _summary(plan, protocol, stage, results)
    write_json(out / "summary.json", summary)
    return summary


def _skills(plan, protocol):
    return [s["skill"] for s in _stages(safe_path(plan["study"]), protocol, plan["method"], plan["stage"])]


def _summary(plan, protocol, stage, results):
    cells = {}
    for target in protocol["order"]:
        ref, result = protocol["references"][target], results[target]
        require(result["benchmark"] == target and result["model_service"] == ref["model_service"],
                "Re-measurement belongs to another domain or model service")
        base = row_index(ref["rows"])
        reused = stage["cells"][target]["result"]["rows"]
        cells[target] = {"remeasured": aggregate(result["rows"], base),
                         "vs_no_skill": paired(result["rows"], base),
                         "reused_observation": aggregate(reused, base),
                         "reused_vs_no_skill": paired(reused, base),
                         "remeasured_vs_reused": paired(result["rows"], row_index(reused)),
                         "new_costs": result["costs"]}
    return seal({"version": VERSION, "protocol_hash": protocol["record_hash"], "method": plan["method"],
                 "stage": plan["stage"], "stage_hash": plan["stage_hash"], "skill_sha256": plan["skill_sha256"],
                 "cells": cells, "new_independent_observation": True, "replaces_reused_cells": False,
                 "data_scope": "previously_exposed_development_not_final", "deployment_authorized": False})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("list", "prepare", "run"))
    parser.add_argument("--output", help="New re-measurement directory outside the study")
    parser.add_argument("--study")
    parser.add_argument("--method", choices=("skillopt", "gepa"))
    parser.add_argument("--stage", type=int)
    parser.add_argument("--repo")
    args = parser.parse_args()
    if args.command == "list":
        print(" ".join(f"{method}:{number}" for method, number in candidates(args.study)))
    elif args.command == "prepare":
        value = prepare(args.study, args.method, args.stage, args.output, args.repo)
        print(json.dumps({"record_hash": value["record_hash"], "skill_bytes": value["skill_bytes"]}))
    else:
        value = run(args.output)
        print(json.dumps({"record_hash": value["record_hash"],
                          "counts": {t: c["remeasured"]["counts"] for t, c in value["cells"].items()}}))


if __name__ == "__main__":
    main()
