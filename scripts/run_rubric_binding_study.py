#!/usr/bin/env python3
"""Verification-note binding study (``fivebench-rubric-binding-study-v1``): does the analyst USE a verification note
when its system prompt makes the note binding? Five arms on one shared train rollout per block (scalar, default
rubric, default rubric + binding, global rubric, global rubric + binding); a bound arm reuses its base arm's reports.
Design: skillopt/feedback_study/rubric_binding.py (written 2026-10-15 before any result).

Usage:
  run_rubric_binding_study.py prepare --template <prepared or completed v10 stage dir> --output <new dir> --blocks N [--series L]
  run_rubric_binding_study.py run     --template <same stage dir> --output <same dir>
  run_rubric_binding_study.py status  --output <dir>
  run_rubric_binding_study.py report  --output <dir>

Same template contract, lock, client check and no-resume rule as scripts/run_rubric_form_study.py.
"""
from __future__ import annotations

import argparse
import fcntl
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.run_rubric_form_study import TEMPLATE_KEYS  # noqa: E402
from skillopt.continual_eval.core import read_json, require, safe_path, write_json  # noqa: E402
from skillopt.validator_pilot.api import digest  # noqa: E402


def spec_from_stage(template_dir, blocks, series=None):
    from skillopt.feedback_study.rubric_binding import build_spec

    root = safe_path(template_dir)
    value = read_json(root / "manifest.json", sealed=True)
    panel = read_json(root / "panel.json")
    record = read_json(root / "stage.json", sealed=True)
    require(record["manifest_hash"] == value["record_hash"] and digest(panel) == value["panel_hash"],
            "The template stage's manifest and panel do not match its record")
    template = {"panel_hash": digest(panel), **{k: value[k] for k in TEMPLATE_KEYS}}
    source = {"template_stage": root.name, "stage_hash": record["record_hash"], "manifest_hash": value["record_hash"],
              "benchmark": value["benchmark"], "parent": record.get("parent"), "selection_source": record.get("selection_source"),
              **({"series": series} if series else {})}
    return build_spec(template, value["benchmark"], blocks, source), panel, record


def prepare(template_dir, output, blocks, series=None):
    from skillopt.feedback_study.rubric_binding import _manifest

    spec, panel, _ = spec_from_stage(template_dir, blocks, series)
    root = safe_path(output) / "study"
    require(not (root / "started.json").exists(), "The study has already started")
    write_json(root / "protocol.json", spec)
    write_json(root / "study.json", _manifest(spec, panel))
    return spec


def run(template_dir, output):
    from scripts import continue_fivebench_baselines as sequence
    from skillopt.feedback_study.rubric_binding import _manifest, run_study

    out = safe_path(output)
    saved = read_json(out / "study" / "protocol.json", sealed=True)
    spec, panel, record = spec_from_stage(template_dir, saved["blocks"], saved["source"].get("series"))
    with safe_path(record["native_lock"]).open("a") as resource:
        fcntl.flock(resource.fileno(), fcntl.LOCK_EX)
        require(saved == spec and read_json(out / "study" / "study.json", sealed=True) == _manifest(spec, panel),
                "The prepared protocol or manifest differs from the one rebuilt from the template and current code")
        sequence.check_client_service(record["repo"], spec["template"]["model"], out / "client-check",
                                      record["learning_model_service"], client_options=record["client_options"])
        result = run_study(spec, panel, out / "study", repo=record["repo"])
        if result["status"] == "completed":
            sequence.verify_service(out / "study", record["learning_model_service"])
    return result


def report(output):
    """Zero calls: the registered analysis of a verified finished study as a compact table."""
    from skillopt.feedback_study.rubric_binding import verify_result

    saved = verify_result(safe_path(output) / "study")
    lines = ["status %s reason %s | blocks %s/%s | costs %s" % (saved["status"], saved["reason"], saved["completed_blocks"],
                                                                 saved["blocks"], {k: saved["costs"].get(k) for k in
                                                                                   ("solver_calls", "reflection_calls", "verifier_calls", "reported_tokens_known_subtotal")})]
    if saved["status"] != "completed":
        return "\n".join(lines)
    p = saved["parent"]
    lines.append("parent on the selection set: %d/%d (unknown %d)" % (p["pass"], p["positions"], p["unknown"]))
    for arm, a in saved["arms"].items():
        lines.append("  %-19s pass %4d/%-4d (unknown %d) yield %.3f | dispositions %s | authorized blocks %s | binding applied %s | blocks with feedback %s" % (
            arm, a["pass"], a["positions"], a["unknown"], a["yield"], a["dispositions"], a["authorized_blocks"], a["binding_applied_blocks"], a["blocks_with_feedback"]))
    for arm, v in saved["verifier_component"].items():
        lines.append("  verifier %-16s detection %s (%s/%s) false rejection %s (%s/%s)" % (
            arm, None if v["detection_rate"] is None else round(v["detection_rate"], 3), v["rejected_host_fail_rows"], v["eligible_host_fail_rows"],
            None if v["false_rejection_rate"] is None else round(v["false_rejection_rate"], 3), v["rejected_host_pass_rows"], v["eligible_host_pass_rows"]))
    for c in saved["contrasts"]:
        bounds = c["unknown_sensitivity_mean_bounds"]
        lines.append("  contrast %-19s - %-13s %s informative %d/%d per block %s (all %s) mean %s | positions wins %d losses %d | block sign-flip p=%.3f (%s) | unknown bounds %s | supported %s" % (
            c["treatment"], c["control"], "PRIMARY" if c["primary"] else "       ", c["informative_blocks"], len(c["all_block_differences"]),
            c["differences"], c["all_block_differences"], None if c["mean_difference"] is None else round(c["mean_difference"], 2),
            c["paired_positions"]["wins"], c["paired_positions"]["losses"], c["block_sign_flip"]["p_value"], c["direction"],
            None if bounds is None else [round(x, 2) for x in bounds], c["supported"]))
    analysis = read_json(safe_path(output) / "study" / "protocol.json", sealed=True)["analysis"]
    lines.append("lead contrast: %s - %s (alpha %s per primary contrast, no correction; only primary contrasts can be "
                 "supported; a yield difference does not establish that the analysts answered the notes)" % (
                     analysis["lead"][0], analysis["lead"][1], analysis["confirmatory"]["alpha"]))
    lines.append("claim limits: " + saved["claim_limits"])
    return "\n".join(lines)


KEYS = ("status", "reason", "completed_blocks", "blocks", "costs")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("prepare")
    p.add_argument("--template", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--blocks", type=int, required=True)
    p.add_argument("--series", help="label of one study of a series (one-block studies pooled by block afterwards)")
    r = sub.add_parser("run")
    r.add_argument("--template", required=True)
    r.add_argument("--output", required=True)
    for name in ("status", "report"):
        sub.add_parser(name).add_argument("--output", required=True)
    args = parser.parse_args(argv)
    if args.command == "prepare":
        spec = prepare(args.template, args.output, args.blocks, args.series)
        print(json.dumps({"protocol_hash": spec["record_hash"], "benchmark": spec["benchmark"], "blocks": spec["blocks"],
                          "arms": spec["arms"], "source": spec["source"]}, indent=1, sort_keys=True))
        return 0
    if args.command == "report":
        print(report(args.output))
        return 0
    if args.command == "run":
        result = run(args.template, args.output)
    else:
        from skillopt.feedback_study.rubric_binding import verify_result

        result = verify_result(safe_path(args.output) / "study")
    print(json.dumps({k: result[k] for k in KEYS if k in result}, indent=1, sort_keys=True))
    return 0 if result["status"] == "completed" else 1


if __name__ == "__main__":
    sys.exit(main())
