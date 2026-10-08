#!/usr/bin/env python3
"""Zero-call, read-only verification of a G stage's recorded test cells (Codex review round 17).

For every named test domain, the stage's sealed test request must equal the request the stage tool builds now for
the Skill the stage deploys (only a reviewed compatible tool hash may differ); its sealed result must bind to that
request, its run directory, the Skill and the cell's sealed checkpoint; and its sealed summary must equal the
summary recomputed from that evidence (recomputed into a scratch directory -- nothing is written into the stage).
Nothing is submitted: a missing or incomplete cell fails. Only a stage with an accepted update has cells of its own.

Usage:
  verify_fivebench_g_cells.py --stage <stage dir> --test-eval <test evaluation dir> [--benchmark B ...]
Exit code 0 only if every cell verifies.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
from pathlib import Path

from skillopt.continual_eval.core import read_json, require, safe_path

DOMAINS = ("searchqa", "bigcodebench", "korbench")
UNBOUND = {"operated_by_tool_sha256", "record_hash"}  # who recomputed it, and the seal over that


def verify_cell(stage, out, record, protocol, learned, test_eval, benchmark):
    tools = {stage._sha(Path(stage.__file__)), *stage.COMPATIBLE_TOOL_HASHES}
    suffix = stage._suffix(record, benchmark)
    request = read_json(out / f"test-request{suffix}.json", sealed=True)
    fresh = stage._test_request(record, protocol, test_eval, out, learned["skill"], benchmark)
    drop = {"tool_sha256", "record_hash"}
    old = {"method": "skillopt", **request}  # the first reviewed predecessor wrote SkillOpt-only requests
    require({k: v for k, v in old.items() if k not in drop} == {k: v for k, v in fresh.items() if k not in drop}
            and request["tool_sha256"] in tools, "Test request is not this stage's request for its deployed Skill")
    result = read_json(out / f"test-result{suffix}.json", sealed=True)
    checkpoint = read_json(safe_path(result["root"]) / f"checkpoints/{stage._method(record)}/h0/s1.json", sealed=True)
    require(result["request_hash"] == request["record_hash"] and result["root"] == request["run"]
            and result["skill_sha256"] == learned["skill_sha256"] == hashlib.sha256(learned["skill"].encode()).hexdigest()
            and checkpoint["skill_text"] == learned["skill"] and checkpoint["provenance"] == request["provenance"]
            and checkpoint["plan_hash"] == result["plan_hash"] and checkpoint["record_hash"] == result["checkpoint_hash"],
            "Recorded test cell does not belong to this request and Skill")
    summary = read_json(out / f"summary{suffix}.json", sealed=True)
    with tempfile.TemporaryDirectory() as scratch:
        recomputed = stage.compare(Path(scratch).resolve(), record, learned, request, result)
    require(summary["operated_by_tool_sha256"] in tools
            and {k: v for k, v in summary.items() if k not in UNBOUND}
            == {k: v for k, v in recomputed.items() if k not in UNBOUND},
            "Recorded summary differs from its sealed test evidence")
    return {"benchmark": benchmark, "skill_sha256": summary["skill_sha256"], "test_counts": summary["test_counts"],
            "wins_vs_no_skill": summary["wins_vs_no_skill"], "losses_vs_no_skill": summary["losses_vs_no_skill"],
            "summary_hash": summary["record_hash"]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--stage", required=True)
    parser.add_argument("--test-eval", required=True)
    parser.add_argument("--benchmark", action="append", choices=DOMAINS)
    args = parser.parse_args(argv)

    from scripts import run_fivebench_g_stage as stage

    out, record, _, protocol, value, _ = stage._load(args.stage)
    learned = stage._recorded_outcome(out, record, value)  # completed stage bound to its sealed result
    require(learned["action"] == "selected_update", "Only a stage with an accepted update has test cells of its own")
    cells = [verify_cell(stage, out, record, protocol, learned, safe_path(args.test_eval), b)
             for b in (args.benchmark or DOMAINS)]
    print(json.dumps({"stage": str(out), "verified_cells": cells}, indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
