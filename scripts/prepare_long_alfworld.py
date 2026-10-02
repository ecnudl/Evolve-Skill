"""Prepare the complete corrected-goal ALFWorld panel at the common model budget.

Zero API calls and zero episodes. Run with the original ALFWorld Python and the
frozen common evaluation package on PYTHONPATH. The native host intentionally
differs from other benchmarks; its dependencies and episode profile stay fixed.
Old responses, scores and interrupted calls are never imported or overwritten.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import inspect
import json
import os
from copy import deepcopy
from pathlib import Path

import httpx

from skillopt.coevolution_v5.core import seal
from skillopt.continual_eval import backends
from skillopt.continual_eval.core import (
    BENCHMARKS,
    freeze_plan,
    load_plan,
    read_json,
    require,
    runtime_identity,
    safe_path,
    source_identity,
    validate_config,
    write_json,
)
from skillopt.continual_eval.datasets import load_panel, panel_hash
from skillopt.continual_eval.datasets import readiness as data_readiness
from skillopt.validator_pilot.api import CachedAPI, digest

VERSION = "long-alfworld-baseline-v1"
TRANSPORT = {"stream": True, "read_timeout_seconds": 300, "stream_wall_seconds": 1800,
             "initial_health_policy": "completed_response_v1"}
PROXY = "http://httpproxy-headless.kubebrain.svc.pjlab.local:3128"
ALF_FUNCTIONS = {"_AlfSession", "_new_alfworld", "_solve_alfworld"}


def _sha(path):
    return hashlib.sha256(safe_path(path).read_bytes()).hexdigest()


def _alf_functions(path):
    values = {node.name: ast.dump(node, include_attributes=False)
              for node in ast.parse(safe_path(path).read_text()).body
              if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name in ALF_FUNCTIONS}
    require(set(values) == ALF_FUNCTIONS, "Corrected ALFWorld implementation missing")
    return digest(values)


def _common(common):
    # load_plan(common) would incorrectly require ALF's native packages to match
    # Coding's host. Bind the shared source/model/service, not that foreign host.
    shared = read_json(common / "plan.json", sealed=True)
    validate_config(shared["config"])
    require(shared["version"] == "continual-eval-v2"
            and source_identity() == shared["source_identity"], "Frozen common source differs")
    model = shared["config"]["model"]
    require(model == {"provider": "bigmodel", "name": "glm-5.3", "max_tokens": 65536,
                      "reasoning_effort": "low", "proxy": PROXY, "transport": TRANSPORT},
            "Unexpected common model/transport")
    service = read_json(common / "model_service.json", sealed=True)
    expected = {"provider": "BIGMODEL", "host": "open.bigmodel.cn", "path": "/api/paas/v4/chat/completions",
                "model": model["name"], "reasoning_effort": "low", "proxy": PROXY, "stream": True,
                "stream_max_wall_seconds": 1800, "initial_health_policy": "completed_response_v1",
                "trust_env": False, "stream_transport": "async-whole-attempt-deadline-v1"}
    require(all(service.get(k) == v and type(service.get(k)) is type(v) for k, v in expected.items())
            and service.get("timeout_seconds", {}).get("read") == 300, "Common service differs")
    # Imports/signature checks only: no client creation, credentials or network.
    require(set(TRANSPORT) <= set(inspect.signature(CachedAPI).parameters)
            and callable(httpx.AsyncClient.stream)
            and runtime_identity()["packages"]["httpx"] == shared["host_runtime"]["packages"]["httpx"],
            "Common HTTP dependency/transport unavailable")
    return shared, service


def _environment(runtime, old_host, panel):
    require(runtime_identity() == old_host, "Use the unchanged original ALFWorld Python environment")
    profile = runtime["alfworld"]
    require(os.environ.get("ALFWORLD_DATA") == profile["alfworld_data"], "Set frozen ALFWORLD_DATA explicitly")
    require(data_readiness(panel)["status"] == "ready"
            and backends.readiness("alfworld", profile)["status"] == "ready", "ALFWorld assets/dependencies not ready")


def prepare(legacy_root, common_run, output):
    legacy, common, root = map(safe_path, (legacy_root, common_run, output))
    source_root = safe_path(Path(backends.__file__).parents[2])
    require(not root.exists() and not any(root.is_relative_to(p) or p.is_relative_to(root)
            for p in (legacy, common, source_root)), "New independent output required")
    old_path = legacy / "run/plan.json"
    old, (shared, service) = read_json(old_path, sealed=True), _common(common)
    require(old["version"] == "continual-eval-v1", "Expected original corrected-goal ALFWorld protocol")
    for plan in (old, shared):
        require(plan["config"]["partition"] == "development" and plan["repeats"] == 2
                and plan["config"]["methods"] == ["no_skill"] and plan["config"]["histories"] == ["h0"],
                "Only complete development No-Skill panels authorized")
    model = shared["config"]["model"]
    require(all(old["config"]["model"][k] == model[k] for k in ("provider", "name", "reasoning_effort", "proxy")),
            "Historical model/service differs beyond output/transport protocol")
    panel_path = safe_path(old["panels"]["alfworld"]["path"])
    panel = load_panel(panel_path)
    require(panel["benchmark"] == "alfworld" and panel["provenance"] == "natural"
            and panel_hash(panel) == old["panels"]["alfworld"]["panel_hash"]
            and len(panel["tasks"]) == len({t["family_id"] for t in panel["tasks"]}) == 39
            and all(t["partition"] == "development" and t["private"]["game_metadata"]["source_split"] == "train"
                    for t in panel["tasks"]), "Original complete train39 development panel required")
    roster = [{"benchmark": "alfworld", **{k: t[k] for k in ("task_id", "family_id", "project_id", "partition")},
               "task_hash": digest(t)} for t in panel["tasks"]]
    require(roster == old["tasks"], "Historical task roster changed")
    runtime = deepcopy(old["config"]["runtime"])
    require(set(runtime) == {"alfworld"} and runtime["alfworld"] == {
        "alfworld_data": runtime["alfworld"].get("alfworld_data"), "alfworld_split": "train",
        "max_steps": 50, "timeout_seconds": 60, "seed": 42}, "Historical native profile differs")
    data_root = safe_path(runtime["alfworld"]["alfworld_data"])
    for task in panel["tasks"]:
        for name in [task["public"]["game_file"], *task["private"]["game_metadata"].get("asset_files", [])]:
            require(safe_path(name).is_relative_to(data_root), "ALFWorld asset outside frozen data root")
    _environment(runtime, old["host_runtime"], panel)
    files = {str(p): _sha(p) for p in (old_path, common / "plan.json", common / "model_service.json", panel_path)}
    vendor = {k for k in shared["source_identity"] if k.startswith("envs/alfworld/vendor/")}
    require("continual_eval/backends.py" in old["source_identity"] and vendor
            and vendor == {k for k in old["source_identity"] if k.startswith("envs/alfworld/vendor/")},
            "Historical ALFWorld source identity incomplete")
    for relative, expected in old["source_identity"].items():
        path = safe_path(legacy / "skillopt" / relative)
        require(path.is_relative_to(legacy / "skillopt") and _sha(path) == expected, "Historical source changed")
        files[str(path)] = expected
        if relative.startswith("envs/alfworld/vendor/"):
            require(shared["source_identity"].get(relative) == expected, "Native ALFWorld vendor changed")
    functions_hash = _alf_functions(legacy / "skillopt/continual_eval/backends.py")
    require(functions_hash == _alf_functions(Path(backends.__file__)), "ALFWorld episode/goal retention implementation changed")
    config = {**deepcopy(shared["config"]), "panels": {b: str(root / "data/panel.json")
        if b == "alfworld" else None for b in BENCHMARKS}, "runtime": runtime, "exposure_manifest": None}
    root.mkdir(parents=True, mode=0o700)
    write_json(root / "data/panel.json", panel)
    write_json(root / "config.json", config)
    plan = freeze_plan(config, root / "run")
    require(plan["source_identity"] == shared["source_identity"] and plan["host_runtime"] == old["host_runtime"],
            "Frozen common implementation/original ALFWorld host differs")
    value = seal({"version": VERSION, "status": "prepared_not_launched", "study_root": str(root),
        "common_run": str(common), "original_files": files,
        "prepared_files": {str(p): _sha(p) for p in root.rglob("*.json")},
        "preparer_sha256": _sha(Path(__file__)), "plan_hash": plan["record_hash"],
        "common_plan_hash": shared["record_hash"], "common_service_hash": service["record_hash"],
        "panel_hash": panel_hash(panel), "alf_functions_hash": functions_hash,
        "alf_host_runtime": plan["host_runtime"], "common_host_runtime": shared["host_runtime"],
        "identical_cross_benchmark_host_claimed": False, "tasks": 39, "families": 39,
        "repeats": 2, "positions": 78, "max_steps": 50, "max_logical_calls": 3900, "model": model,
        "evidence_kind": "natural_development_baseline_same_historically_exposed_train_panel",
        "model_calls": 0, "episodes_started": 0, "workers": 2,
        "lock_requirement": "hold_common_native_and_s1_method_locks_across_generate_and_score",
        "native_memory_hard_limit": None, "native_environment_upgraded": False,
        "old_answers_imported": False, "old_scores_replaced": False, "old_open_calls_resumed": False,
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
    shared, service = _common(safe_path(value["common_run"]))
    require(plan["record_hash"] == value["plan_hash"] and shared["record_hash"] == value["common_plan_hash"]
            and service["record_hash"] == value["common_service_hash"], "Plan/service identity changed")
    _environment(plan["config"]["runtime"], value["alf_host_runtime"], load_panel(root / "data/panel.json"))
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
    print(json.dumps({k: value[k] for k in ("record_hash", "plan_hash", "tasks", "positions", "model_calls", "episodes_started")}
                     | {"status": "validated_not_launched" if args.check else value["status"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
