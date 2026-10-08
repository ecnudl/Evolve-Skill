#!/usr/bin/env python3
"""L1 fixed-rubric study (``fivebench-fixed-rubric-study-v1``; registered 10/8, Codex design round post-S3-2).
See skillopt/feedback_study/fixed_rubric.py for the registered design.

Usage:
  run_fivebench_fixed_rubric_study.py prepare --source <completed v10 KOR stage> --output <new dir>
  run_fivebench_fixed_rubric_study.py run --source <same stage> --output <same dir>
  run_fivebench_fixed_rubric_study.py status --output <dir>

prepare (zero calls): verifies the completed source stage against its sealed result and evidence inventory, takes
its three evolved KOR rubric records (steps 0-2; the last must be the stage's final rubric) and the frozen default,
and writes the sealed protocol and the study manifest into <output>/study. run: rebuilds the identical protocol
from the source, takes F's native lock, checks the client service against the source's frozen service and runs the
study once (an interrupted study is never resumed). status: verifies the finished result against its own sealed
protocol, manifest and exact evidence inventory before printing it. Exit code 0 only for a completed study.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import sys

from skillopt.continual_eval.core import read_json, require, safe_path, write_json


def spec_from_stage(source):
    """Zero-call: (spec, panel, stage record) of a completed v10 KOR stage, every input bound to sealed evidence."""
    from scripts import run_fivebench_g_stage as stage
    from skillopt.continual_learning.verifier import default_policy_record
    from skillopt.feedback_study.fixed_rubric import BENCHMARK, build_spec
    from skillopt.validator_pilot.api import digest

    out, record, _, _, value, panel = stage._load(source)
    learned = stage._recorded_outcome(out, record, value)  # completed stage bound to its sealed result
    result = read_json(out / "learning" / "result.json", sealed=True)
    require(value["method"] == "rubric_research" and record["benchmark"] == BENCHMARK
            and learned["status"] == result["status"] == "completed" and len(learned["verifier_steps"]) == 3,
            "The source is a completed three-step v10 KOR-Bench stage")
    rubrics = {"default": default_policy_record(BENCHMARK)}
    summaries = []
    for step, arm in enumerate(("h0", "h1", "h2")):
        policy = read_json(out / "learning" / "verifier" / str(step) / "policy.json", sealed=True)
        summary = read_json(out / "learning" / "verifier" / str(step) / "summary.json", sealed=True)
        require(policy["manifest_hash"] == summary["manifest_hash"] == value["record_hash"]
                and policy["step"] == summary["step"] == step and summary["policy_hash"] == policy["policy_hash"]
                and learned["verifier_steps"][step]["record_hash"] == summary["record_hash"],
                "A rubric record is not the source step's sealed policy")
        rubrics[arm] = policy
        summaries.append(summary["record_hash"])
    require(result["verifier_policy"][BENCHMARK]["policy_hash"] == rubrics["h2"]["policy_hash"],
            "h2 is not the source stage's final KOR rubric")
    template = {"panel_hash": digest(panel), "train_families": value["train_families"],
                "selection_families": value["selection_families"], "model": value["model"], "runtime": value["runtime"],
                "parent_skill": value["parent_skill"], "seed": value["seed"], "recovery_policy": value["recovery_policy"]}
    source_binding = {"stage_dir": str(out), "stage_record_hash": record["record_hash"],
                      "learned_record_hash": learned["record_hash"], "learning_result_hash": result["record_hash"],
                      "manifest_hash": value["record_hash"], "verifier_summary_hashes": summaries,
                      "parent_skill_sha256": hashlib.sha256(value["parent_skill"].encode()).hexdigest()}
    return build_spec(template, rubrics, source_binding), panel, record


def prepare(source, output):
    from skillopt.feedback_study.fixed_rubric import _manifest

    spec, panel, _ = spec_from_stage(source)
    root = safe_path(output) / "study"
    require(not (root / "started.json").exists(), "The study has already started")
    write_json(root / "protocol.json", spec)
    write_json(root / "study.json", _manifest(spec, panel))  # the rebuilt v10 manifest validates the panel/assets
    return spec


def run(source, output):
    from scripts import continue_fivebench_baselines as sequence
    from skillopt.feedback_study.fixed_rubric import run_study

    spec, panel, record = spec_from_stage(source)
    out = safe_path(output)
    require(read_json(out / "study" / "protocol.json", sealed=True) == spec,
            "The prepared protocol differs from the one rebuilt from the source")
    with safe_path(record["native_lock"]).open("a") as resource:
        fcntl.flock(resource.fileno(), fcntl.LOCK_EX)
        sequence.check_client_service(record["repo"], spec["template"]["model"], out / "client-check",
                                      record["learning_model_service"], client_options=record["client_options"])
        result = run_study(spec, panel, out / "study", repo=record["repo"])
        if result["status"] == "completed":
            sequence.verify_service(out / "study", record["learning_model_service"])
    return result


KEYS = ("status", "reason", "train_tasks", "eligible_rows", "source_unknown_rows", "eligible_host_fail_rows",
        "eligible_host_pass_rows", "primary", "safety", "secondary_mcnemar", "registered_wording", "audit", "costs")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("prepare", "run"):
        command = sub.add_parser(name)
        command.add_argument("--source", required=True)
        command.add_argument("--output", required=True)
    sub.add_parser("status").add_argument("--output", required=True)
    args = parser.parse_args(argv)
    if args.command == "prepare":
        spec = prepare(args.source, args.output)
        print(json.dumps({"protocol_hash": spec["record_hash"], "rubric_policy_hashes": spec["rubric_policy_hashes"],
                          "rubric_record_hashes": {arm: r.get("record_hash") for arm, r in spec["rubrics"].items()},
                          "train_families": len(spec["template"]["train_families"]),
                          "source": spec["source"], "budget": spec["budget"]}, indent=1, sort_keys=True))
        return 0
    if args.command == "run":
        result = run(args.source, args.output)
    else:
        from skillopt.feedback_study.fixed_rubric import verify_result

        result = verify_result(safe_path(args.output) / "study")  # bindings + exact evidence inventory, zero calls
    summary = {k: result[k] for k in KEYS if k in result}
    if "arms" in result:
        summary["arms"] = {arm: {k: v for k, v in metrics.items() if k not in {"v7_conditional"}}
                           for arm, metrics in result["arms"].items()}
    print(json.dumps(summary, indent=1, sort_keys=True))
    return 0 if result["status"] == "completed" else 1


if __name__ == "__main__":
    sys.exit(main())
