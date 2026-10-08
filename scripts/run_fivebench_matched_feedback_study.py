#!/usr/bin/env python3
"""L3 matched one-step feedback study (``fivebench-matched-feedback-study-v1``; registered 10/8, Codex design round
post-S3-2). See skillopt/feedback_study/matched_feedback.py for the registered design.

Usage:
  run_fivebench_matched_feedback_study.py prepare --source <completed v10 KOR stage> --output <new dir>
  run_fivebench_matched_feedback_study.py run --source <same stage> --output <same dir>
  run_fivebench_matched_feedback_study.py status --output <dir>

prepare (zero calls): the source stage is verified exactly as for L1 (run_fivebench_fixed_rubric_study.spec_from_stage:
the completed stage against its sealed result and evidence inventory, its step rubrics against the step summaries and
the stage's final rubric); the L3 protocol takes the frozen default and the final evolved rubric (h2) and is written
with the study manifest into <output>/study. run: rebuilds the identical protocol, takes F's native lock, checks the
client service against the source's frozen service and runs the study once (never resumed). status: verifies the
finished result against its own sealed protocol, manifest and exact evidence inventory. Exit 0 only when completed.
"""
from __future__ import annotations

import argparse
import fcntl
import json
import sys

from skillopt.continual_eval.core import read_json, require, safe_path, write_json


def spec_from_stage(source):
    from scripts.run_fivebench_fixed_rubric_study import spec_from_stage as verified_inputs
    from skillopt.feedback_study.matched_feedback import build_spec

    l1, panel, record = verified_inputs(source)  # the reviewed L1 source verification, zero calls
    rubrics = {"default": l1["rubrics"]["default"], "h2": l1["rubrics"]["h2"]}
    return build_spec(l1["template"], rubrics, l1["source"]), panel, record


def prepare(source, output):
    from skillopt.feedback_study.matched_feedback import _manifest

    spec, panel, _ = spec_from_stage(source)
    root = safe_path(output) / "study"
    require(not (root / "started.json").exists(), "The study has already started")
    write_json(root / "protocol.json", spec)
    write_json(root / "study.json", _manifest(spec, panel))
    return spec


def run(source, output):
    from scripts import continue_fivebench_baselines as sequence
    from skillopt.feedback_study.matched_feedback import _manifest, run_study

    spec, panel, record = spec_from_stage(source)
    out = safe_path(output)
    with safe_path(record["native_lock"]).open("a") as resource:
        fcntl.flock(resource.fileno(), fcntl.LOCK_EX)
        # the prepared protocol AND manifest (incl. the implementation identity) must equal the current rebuild,
        # checked under the lock before any client is constructed
        require(read_json(out / "study" / "protocol.json", sealed=True) == spec
                and read_json(out / "study" / "study.json", sealed=True) == _manifest(spec, panel),
                "The prepared protocol or manifest differs from the one rebuilt from the source and current code")
        sequence.check_client_service(record["repo"], spec["template"]["model"], out / "client-check",
                                      record["learning_model_service"], client_options=record["client_options"])
        result = run_study(spec, panel, out / "study", repo=record["repo"])
        if result["status"] == "completed":
            sequence.verify_service(out / "study", record["learning_model_service"])
    return result


KEYS = ("status", "reason", "completed_blocks", "primary", "secondary", "arms", "registered_wording",
        "usage_complete", "unknown_cost_attempts", "costs")


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
                          "blocks": spec["blocks"], "source": spec["source"], "budget": spec["budget"]},
                         indent=1, sort_keys=True))
        return 0
    if args.command == "run":
        result = run(args.source, args.output)
    else:
        from skillopt.feedback_study.matched_feedback import verify_result

        result = verify_result(safe_path(args.output) / "study")
    print(json.dumps({k: result[k] for k in KEYS if k in result}, indent=1, sort_keys=True))
    return 0 if result["status"] == "completed" else 1


if __name__ == "__main__":
    sys.exit(main())
