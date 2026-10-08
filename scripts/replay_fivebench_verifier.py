#!/usr/bin/env python3
"""Paid frozen-train verifier replay (registered 10/8, Codex design rounds 1-2; mechanism screen for a verifier
change, not a learning stage). See skillopt/continual_learning/verifier_replay.py.

Usage:
  replay_fivebench_verifier.py --source <completed v10 BigCodeBench stage dir> --step 0 --output <new dir>
                               --require FILE::TEXT [...] --forbid FILE::TEXT [...]

The source stage is first verified read-only against its sealed record and evidence inventory (zero calls). Every
--require marker (a queue-log line proving that the prespecified main table is complete) must be present and every
--forbid marker (a queue STOP) absent, checked before and again after taking F's native lock, which is then held for
the whole replay -- a free lock alone is not completion. The
replay writes only into the new output directory; an interrupted replay is never resumed and is inconclusive.
Exit code 0 only for a completed replay.
"""
from __future__ import annotations

import argparse
import fcntl
import json
import sys

from skillopt.continual_eval.core import require, safe_path


def _markers(requirements, forbidden=()):
    """Every required FILE::TEXT line is present and no forbidden one (a queue STOP) is."""
    for item in requirements:
        path, sep, text = item.partition("::")
        require(bool(sep) and bool(text), "A --require marker is FILE::TEXT")
        require(text in safe_path(path).read_text(errors="replace"), "Required completion marker missing: " + item)
    for item in forbidden:
        path, sep, text = item.partition("::")
        require(bool(sep) and bool(text), "A --forbid marker is FILE::TEXT")
        require(text not in safe_path(path).read_text(errors="replace"), "Forbidden marker present: " + item)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source", required=True)
    parser.add_argument("--step", type=int, default=0)
    parser.add_argument("--output", required=True)
    parser.add_argument("--require", action="append", required=True,
                        help="FILE::TEXT completion marker of the prespecified main table (repeat; at least one)")
    parser.add_argument("--forbid", action="append", required=True,
                        help="FILE::TEXT that must NOT be present, e.g. a main-table queue STOP (repeat; at least one)")
    args = parser.parse_args(argv)

    from scripts import run_fivebench_g_stage as stage
    from skillopt.continual_learning.verifier_replay import overlaps, replay_step

    require(bool(args.require) and bool(args.forbid), "The registered replay needs completion and STOP markers")
    out, record, _, _, value, _ = stage._load(args.source)
    output = safe_path(args.output)
    require(not overlaps(out, output), "The replay output must not overlap the archived source stage")
    stage._recorded_outcome(out, record, value)  # completed stage bound to its sealed result (zero calls)
    require(value["method"] == "rubric_research" and record["benchmark"] == "bigcodebench",
            "The replay source is a v10 BigCodeBench stage")
    _markers(args.require, args.forbid)
    sequence = stage._sequence()
    with safe_path(record["native_lock"]).open("a") as resource:
        fcntl.flock(resource.fileno(), fcntl.LOCK_EX)
        _markers(args.require, args.forbid)  # still complete and unstopped now that the lock is held
        sequence.check_client_service(record["repo"], value["model"], output / "client-check",
                                      record["learning_model_service"], client_options=record["client_options"])
        result = replay_step(out / "learning", args.step, output / "replay", repo=record["repo"])
        if result["status"] == "completed":
            sequence.verify_service(output / "replay", record["learning_model_service"])
    keys = ("status", "reason", "eligible_rows", "source_unknown_rows", "policy_status", "authorized", "detections",
            "false_rejections", "host_pass_rows", "host_fail_rows", "structure_admission", "by_kind", "coverage",
            "delivery", "criteria", "structural_detections_for_audit", "reports_with_feedback")
    print(json.dumps({k: result[k] for k in keys if k in result}, indent=1, sort_keys=True))
    return 0 if result["status"] == "completed" else 1


if __name__ == "__main__":
    sys.exit(main())
