"""Freeze the complete old SearchQA development panel under the common v2 budget.

Preparation is offline. No historical model responses are imported and no Skill is
selected. Run with the same frozen evaluation package as the Coding baseline.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from copy import deepcopy
from pathlib import Path

from skillopt.coevolution_v5.core import seal
from skillopt.continual_eval.core import BENCHMARKS, freeze_plan, load_plan, read_json, require, safe_path, write_json
from skillopt.continual_eval.datasets import load_panel, panel_hash
from skillopt.validator_pilot.api import digest


def _sha(path):
    return hashlib.sha256(safe_path(path).read_bytes()).hexdigest()


def prepare(legacy_root, common_run, output):
    legacy, common, root = map(safe_path, (legacy_root, common_run, output))
    require(not root.exists() and not any(root.is_relative_to(p) or p.is_relative_to(root)
                                        for p in (legacy, common)), "New independent output required")
    old_path = legacy / "run/plan.json"
    old, shared = read_json(old_path, sealed=True), load_plan(common)
    require(old["version"] == "continual-eval-v1" and shared["version"] == "continual-eval-v2",
            "Expected the old SearchQA and new common-budget protocols")
    for plan in (old, shared):
        require(plan["config"]["partition"] == "development" and plan["repeats"] == 2
                and plan["config"]["methods"] == ["no_skill"] and plan["config"]["histories"] == ["h0"],
                "Only the complete development No-Skill panel is authorized")
    model = shared["config"]["model"]
    require(model["provider"] == "bigmodel" and model["name"] == "glm-5.3"
            and model["reasoning_effort"] == "low" and model["max_tokens"] == 65536
            and model["transport"] == {"stream": True, "read_timeout_seconds": 300,
                "stream_wall_seconds": 1800, "initial_health_policy": "completed_response_v1"},
            "Unexpected common model/transport")
    panel_path = safe_path(old["panels"]["searchqa"]["path"])
    panel = load_panel(panel_path)
    require(panel["benchmark"] == "searchqa" and panel["provenance"] == "natural"
            and panel_hash(panel) == old["panels"]["searchqa"]["panel_hash"]
            and len(panel["tasks"]) == 400
            and all(t["partition"] == "development" for t in panel["tasks"]), "Original complete panel required")
    roster = [{"benchmark": "searchqa", **{k: t[k] for k in ("task_id", "family_id", "project_id", "partition")},
               "task_hash": digest(t)} for t in panel["tasks"]]
    require(roster == old["tasks"], "Historical task roster changed")
    files = {str(p): _sha(p) for p in (old_path, common / "plan.json", panel_path)}
    for relative, expected in old["source_identity"].items():
        path = safe_path(legacy / "skillopt" / relative)
        require(path.is_relative_to(legacy / "skillopt") and _sha(path) == expected, "Historical source changed")
        files[str(path)] = expected
    config = {**deepcopy(shared["config"]), "panels": {b: str(root / "data/panel.json")
        if b == "searchqa" else None for b in BENCHMARKS}, "runtime": deepcopy(old["config"]["runtime"]),
        "exposure_manifest": None}
    require(not config["runtime"], "The source SearchQA protocol must use its native text scorer")
    root.mkdir(parents=True, mode=0o700)
    write_json(root / "data/panel.json", panel)
    write_json(root / "config.json", config)
    plan = freeze_plan(config, root / "run")
    require(plan["source_identity"] == shared["source_identity"] and plan["host_runtime"] == shared["host_runtime"],
            "Frozen common evaluation implementation/runtime differs")
    prepared = {str(p): _sha(p) for p in root.rglob("*.json")}
    receipt = seal({"version": "long-searchqa-baseline-v1", "status": "prepared_not_launched",
        "study_root": str(root), "common_run": str(common), "original_files": files, "prepared_files": prepared,
        "preparer_sha256": _sha(Path(__file__)), "plan_hash": plan["record_hash"],
        "common_plan_hash": shared["record_hash"], "panel_hash": panel_hash(panel),
        "tasks": 400, "repeats": 2, "positions": 800, "model": model,
        "evidence_kind": "natural_development_baseline_same_historically_exposed_panel",
        "model_calls": 0, "workers": 6, "old_answers_imported": False, "old_scores_replaced": False,
        "causal_budget_effect_claimed": False, "skill_updated": False, "deployment_authorized": False})
    write_json(root / "preparation.json", receipt)
    return receipt


def check(output):
    root = safe_path(output)
    value = read_json(root / "preparation.json", sealed=True)
    require(value["version"] == "long-searchqa-baseline-v1" and value["study_root"] == str(root)
            and value["preparer_sha256"] == _sha(Path(__file__)), "Preparation/source binding changed")
    for field in ("original_files", "prepared_files"):
        require(all(_sha(Path(p)) == expected for p, expected in value[field].items()), "Frozen inputs changed")
    require(load_plan(root / "run")["record_hash"] == value["plan_hash"]
            and load_plan(value["common_run"])["record_hash"] == value["common_plan_hash"], "Plan identity changed")
    return value


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    parser.add_argument("--legacy-root")
    parser.add_argument("--common-run")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    if not args.check:
        require(args.legacy_root and args.common_run, "Legacy source and common run required")
    value = check(args.output) if args.check else prepare(args.legacy_root, args.common_run, args.output)
    print(json.dumps({k: value[k] for k in ("record_hash", "plan_hash", "tasks", "positions", "model_calls")}
                     | {"status": "validated_not_launched" if args.check else value["status"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
