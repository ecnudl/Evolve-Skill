"""Freeze all 500 old KORBench development tasks at the common Solver budget.

No historical responses/scores are read or imported. Native scorer and its
resource budget remain unchanged. This is not a truncation-subset recovery or
a causal budget experiment. Execute from the frozen common evaluation package.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from copy import deepcopy
from pathlib import Path

from skillopt.coevolution_v5.core import seal
from skillopt.continual_eval.backends import _kor_sources
from skillopt.continual_eval.core import BENCHMARKS, freeze_plan, load_plan, read_json, require, safe_path, write_json
from skillopt.continual_eval.datasets import load_panel, panel_hash
from skillopt.validator_pilot.api import digest

VERSION = "long-korbench-baseline-v1"
CATEGORIES = {"logic", "operation", "puzzle", "cipher", "counterfactual"}


def _sha(path):
    return hashlib.sha256(safe_path(path).read_bytes()).hexdigest()


def prepare(legacy_root, common_run, output):
    legacy, common, root = map(safe_path, (legacy_root, common_run, output))
    require(not root.exists() and not any(root.is_relative_to(p) or p.is_relative_to(root)
                                        for p in (legacy, common)), "New independent output required")
    old_path = legacy / "korbench-run/plan.json"
    old, shared = read_json(old_path, sealed=True), load_plan(common)
    require(old["version"] == "continual-eval-v1" and shared["version"] == "continual-eval-v2",
            "Expected old KORBench and new common-budget protocols")
    for plan in (old, shared):
        require(plan["config"]["partition"] == "development" and plan["repeats"] == 2
                and plan["config"]["methods"] == ["no_skill"] and plan["config"]["histories"] == ["h0"],
                "Only complete development No-Skill panels authorized")
    model = shared["config"]["model"]
    require(model["provider"] == "bigmodel" and model["name"] == "glm-5.3"
            and model["reasoning_effort"] == "low" and model["max_tokens"] == 65536
            and model["transport"] == {"stream": True, "read_timeout_seconds": 300,
                "stream_wall_seconds": 1800, "initial_health_policy": "completed_response_v1"},
            "Unexpected common model/transport")
    require(all(old["config"]["model"][k] == model[k] for k in ("provider", "name", "reasoning_effort")),
            "Historical model differs beyond output/transport protocol")
    panel_path = safe_path(old["panels"]["korbench"]["path"])
    panel = load_panel(panel_path)
    require(panel["benchmark"] == "korbench" and panel["provenance"] == "natural"
            and panel_hash(panel) == old["panels"]["korbench"]["panel_hash"]
            and len(panel["tasks"]) == 500 and len({t["family_id"] for t in panel["tasks"]}) == 50
            and all(t["partition"] == "development" for t in panel["tasks"]), "Original complete panel required")
    require(Counter(t["private"]["category"] for t in panel["tasks"]) == dict.fromkeys(CATEGORIES, 100),
            "Original five-category distribution required")
    roster = [{"benchmark": "korbench", **{k: t[k] for k in ("task_id", "family_id", "project_id", "partition")},
               "task_hash": digest(t)} for t in panel["tasks"]]
    require(roster == old["tasks"], "Historical task roster changed")
    runtime = deepcopy(old["config"]["runtime"])
    require(set(runtime) == {"korbench"} and runtime["korbench"]["timeout_seconds"] == 300
            and runtime["korbench"]["memory_mb"] == 4096 and runtime["korbench"]["cpus"] == 1,
            "Historical native resource profile differs")
    # This only reads/verifies scorer source files; it never imports/evaluates
    # benchmark expressions in the host or starts Docker during preparation.
    native = digest(_kor_sources(runtime["korbench"]))
    files = {str(p): _sha(p) for p in (old_path, common / "plan.json", panel_path)}
    for relative, expected in old["source_identity"].items():
        path = safe_path(legacy / "skillopt" / relative)
        require(path.is_relative_to(legacy / "skillopt") and _sha(path) == expected, "Historical source changed")
        files[str(path)] = expected
    config = {**deepcopy(shared["config"]), "panels": {b: str(root / "data/panel.json")
        if b == "korbench" else None for b in BENCHMARKS}, "runtime": runtime, "exposure_manifest": None}
    root.mkdir(parents=True, mode=0o700)
    write_json(root / "data/panel.json", panel)
    write_json(root / "config.json", config)
    plan = freeze_plan(config, root / "run")
    require(plan["source_identity"] == shared["source_identity"] and plan["host_runtime"] == shared["host_runtime"],
            "Frozen common evaluation implementation/runtime differs")
    prepared = {str(p): _sha(p) for p in root.rglob("*.json")}
    value = seal({"version": VERSION, "status": "prepared_not_launched", "study_root": str(root),
        "common_run": str(common), "original_files": files, "prepared_files": prepared,
        "preparer_sha256": _sha(Path(__file__)), "plan_hash": plan["record_hash"],
        "common_plan_hash": shared["record_hash"], "panel_hash": panel_hash(panel), "native_sources_hash": native,
        "tasks": 500, "families": 50, "repeats": 2, "positions": 1000, "model": model,
        "evidence_kind": "natural_development_baseline_same_historically_exposed_panel",
        "model_calls": 0, "workers": 6, "old_answers_imported": False, "old_scores_replaced": False,
        "causal_budget_effect_claimed": False, "skill_updated": False, "deployment_authorized": False})
    write_json(root / "preparation.json", value)
    return value


def check(output):
    root = safe_path(output)
    value = read_json(root / "preparation.json", sealed=True)
    require(value["version"] == VERSION and value["study_root"] == str(root)
            and value["preparer_sha256"] == _sha(Path(__file__)), "Preparation/source binding changed")
    for field in ("original_files", "prepared_files"):
        require(all(_sha(Path(p)) == expected for p, expected in value[field].items()), "Frozen inputs changed")
    plan = load_plan(root / "run")
    require(plan["record_hash"] == value["plan_hash"]
            and load_plan(value["common_run"])["record_hash"] == value["common_plan_hash"]
            and digest(_kor_sources(plan["config"]["runtime"]["korbench"])) == value["native_sources_hash"],
            "Plan/native scorer identity changed")
    return value


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    parser.add_argument("--legacy-root")
    parser.add_argument("--common-run")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    require(args.check or (args.legacy_root and args.common_run), "Legacy source and common run required")
    value = check(args.output) if args.check else prepare(args.legacy_root, args.common_run, args.output)
    print(json.dumps({k: value[k] for k in ("record_hash", "plan_hash", "tasks", "positions", "model_calls")}
                     | {"status": "validated_not_launched" if args.check else value["status"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
