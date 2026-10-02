"""Freeze a new BCB development baseline study; no model calls or scoring.

The same historically exposed panels/roles are reused, not new holdouts. Old
receipts are not imported, and no old learner is resumed. Run this module from
the new frozen source snapshot; --check validates a prepared study before launch.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from copy import deepcopy
from pathlib import Path

from skillopt.coevolution_v5.core import seal
from skillopt.continual_eval.core import (
    BENCHMARKS,
    freeze_plan,
    load_plan,
    read_json,
    require,
    safe_path,
    write_json,
)
from skillopt.continual_eval.datasets import load_panel, panel_hash
from skillopt.continual_learning.contracts import manifest, sources, validate_manifest
from skillopt.continual_learning.skillopt import native_sources
from skillopt.validator_pilot.api import digest

VERSION = "long-baseline-study-v1"
PROXY = "http://httpproxy-headless.kubebrain.svc.pjlab.local:3128"
TRANSPORT = {"stream": True, "read_timeout_seconds": 300, "stream_wall_seconds": 1800,
             "initial_health_policy": "completed_response_v1"}
OLD_BUDGET = {"max_metric_calls": 512, "max_reflection_calls": 32, "max_api_calls": 600,
              "max_reported_tokens": 2000000, "max_iterations": 2, "minibatch_size": 8,
              "solver_max_tokens": 4096, "reflection_max_tokens": 4096}


def _sha(path):
    return hashlib.sha256(safe_path(path).read_bytes()).hexdigest()


def _source_root():
    return safe_path(Path(__file__).resolve().parents[1])


def _source_files(root, declared):
    require(type(declared) is dict and declared, "Frozen source identity missing")
    files = {}
    for relative, expected in declared.items():
        path = safe_path(root / "skillopt" / relative)
        require(path.is_relative_to(root / "skillopt") and _sha(path) == expected, "Frozen source changed")
        files[str(path)] = expected
    return files


def prepare(output, *, legacy_learning_root, legacy_no_skill_root):
    root, source = safe_path(output), _source_root()
    old_learning, old_eval = safe_path(legacy_learning_root), safe_path(legacy_no_skill_root)
    require(not root.exists() and not any(root.is_relative_to(p) for p in (source, old_learning, old_eval)),
            "Use a new study directory outside all source and historical directories")
    learning_path, plan_path = old_learning / "data/panel.json", old_eval / "run/plan.json"
    panel, old_plan = load_panel(learning_path), read_json(plan_path, sealed=True)
    require(old_plan["version"] == "continual-eval-v1" and old_plan["config"]["partition"] == "development"
            and old_plan["repeats"] == 2, "Expected the frozen development v1 baseline")
    eval_path = safe_path(old_plan["panels"]["bigcodebench"]["path"])
    evaluation = load_panel(eval_path)
    require(old_plan["panels"]["bigcodebench"]["panel_hash"] == panel_hash(evaluation), "Old evaluation panel changed")
    for data in (panel, evaluation):
        require(data["benchmark"] == "bigcodebench" and data["provenance"] == "natural"
                and all(t["partition"] == "development" for t in data["tasks"]),
                "Only the original natural Coding development panels are authorized")
    require(len(evaluation["tasks"]) == 400 and len(panel["tasks"]) == 129, "Frozen task counts differ")
    roster = [{"benchmark": "bigcodebench", **{k: t[k] for k in
               ("task_id", "family_id", "project_id", "partition")}, "task_hash": digest(t)} for t in evaluation["tasks"]]
    require([t for t in old_plan["tasks"] if t["benchmark"] == "bigcodebench"] == roster,
            "Old evaluation roster differs from its panel")
    full = {t["task_id"]: t for t in evaluation["tasks"]}
    require(all(full.get(t["task_id"]) == t for t in panel["tasks"]), "Learning tasks differ from original development data")
    original_files = {str(p): _sha(p) for p in (learning_path, plan_path, eval_path)}
    original_files.update(_source_files(old_eval, old_plan["source_identity"]))
    old_manifests = {}
    for method in ("skillopt", "gepa"):
        path = old_learning / "manifests" / (method + ".json")
        value = read_json(path, sealed=True)
        require(value["version"] == "continual-learning-gepa-v1" and value["method"] == method
                and value["panel_hash"] == digest(panel) and value["parent_skill"] == ""
                and value["budget"] == OLD_BUDGET, "Old learning protocol/budget differs")
        require(len(value["train_families"]) == len(set(value["train_families"])) == 64
                and len(value["selection_families"]) == len(set(value["selection_families"])) == 64
                and not set(value["train_families"]) & set(value["selection_families"]), "Old role families differ")
        roles = {digest(t): "train" if t["family_id"] in value["train_families"] else "selection" for t in panel["tasks"]}
        require(value["authorized_tasks"] == roles and list(roles.values()).count("train") == 65
                and list(roles.values()).count("selection") == 64, "Old task-role authorization differs")
        require(value["model"] == old_plan["config"]["model"]
                and value["runtime"] == old_plan["config"]["runtime"]["bigcodebench"], "Historical model/runtime differ")
        original_files[str(path)] = _sha(path)
        original_files.update(_source_files(old_learning, value["source_identity"]))
        old_manifests[method] = value
    common_keys = ("train_families", "selection_families", "model", "budget", "runtime", "seed", "parent_skill")
    first = old_manifests["skillopt"]
    require(all(first[k] == old_manifests["gepa"][k] for k in common_keys), "Methods lack a common frozen protocol")
    require(first["model"] == {"provider": "bigmodel", "name": "glm-5.3", "max_tokens": 4096,
                                "reasoning_effort": "low", "proxy": PROXY}, "Unexpected historical model/proxy")
    model = {**deepcopy(first["model"]), "max_tokens": 65536, "transport": deepcopy(TRANSPORT)}
    budget = {**OLD_BUDGET, "solver_max_tokens": 65536}
    new_manifests = {method: manifest(panel, version="continual-learning-v2", method=method,
                    train_families=first["train_families"], selection_families=first["selection_families"],
                    model=deepcopy(model), budget=deepcopy(budget), runtime=deepcopy(first["runtime"]),
                    parent_skill="", seed=first["seed"]) for method in ("skillopt", "gepa")}
    current_files = _source_files(source, {**sources(), **native_sources()})
    current_files.update({str(source / "scripts" / name): _sha(source / "scripts" / name)
                          for name in ("prepare_long_baselines.py", "run_long_baselines_linux.sh", "run_continual_learning.py")})
    # All validation precedes creation; a partial output is never overwritten.
    root.mkdir(parents=True, mode=0o700)
    write_json(root / "data/learning.json", panel)
    write_json(root / "data/evaluation.json", evaluation)
    for method, value in new_manifests.items():
        write_json(root / "manifests" / (method + ".json"), value)
    config = {**deepcopy(old_plan["config"]), "version": "continual-eval-v2",
              "panels": {b: str(root / "data/evaluation.json") if b == "bigcodebench" else None for b in BENCHMARKS},
              "methods": ["no_skill"], "histories": ["h0"], "repeats": 2, "model": model,
              "runtime": {"bigcodebench": deepcopy(first["runtime"])}, "exposure_manifest": None}
    write_json(root / "evaluation.config.json", config)
    plan = freeze_plan(config, root / "no_skill")
    prepared_files = {str(p): _sha(p) for p in root.rglob("*.json")}
    receipt = seal({"version": VERSION, "status": "prepared_not_launched", "model_calls": 0,
                    "source_root": str(source), "study_root": str(root), "source_files": current_files,
                    "original_files": original_files, "prepared_files": prepared_files,
                    "old_manifest_hashes": {m: v["record_hash"] for m, v in old_manifests.items()},
                    "new_manifest_hashes": {m: v["record_hash"] for m, v in new_manifests.items()},
                    "evaluation_plan_hash": plan["record_hash"], "evaluation_tasks": 400, "evaluation_positions": 800,
                    "train_tasks": 65, "train_families": 64, "selection_tasks": 64, "selection_families": 64,
                    "data_provenance": "same_historically_exposed_development_panels_not_new_holdout",
                    "old_answers_imported": False, "old_scores_replaced": False, "optimizer_resumed": False,
                    "deployment_authorized": False, "s1_evaluation_authorized": False,
                    "model": model, "budget_each": budget, "solver_workers": 1, "no_skill_workers": 6,
                    "native_lock": str(root / "native.lock"), "actual_compute_matched": False})
    write_json(root / "preparation.json", receipt)
    return receipt


def check(output):
    root = safe_path(output)
    value = read_json(root / "preparation.json", sealed=True)
    require(value["version"] == VERSION and value["source_root"] == str(_source_root())
            and value["study_root"] == str(root), "Study source/root binding changed")
    for key in ("source_files", "original_files", "prepared_files"):
        require(all(_sha(Path(path)) == expected for path, expected in value[key].items()), "Frozen study inputs changed")
    require(load_plan(root / "no_skill")["record_hash"] == value["evaluation_plan_hash"], "Study evaluation plan changed")
    panel = load_panel(root / "data/learning.json")
    for method in ("skillopt", "gepa"):
        current = validate_manifest(read_json(root / "manifests" / (method + ".json"), sealed=True), panel)
        require(current["record_hash"] == value["new_manifest_hashes"][method], "Study learning manifest changed")
    return value


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--legacy-learning-root", default="/root/continual-learning-bcb-20260928-a")
    parser.add_argument("--legacy-no-skill-root", default="/root/continual-noskill-bcb-20260928-a")
    args = parser.parse_args(argv)
    value = check(args.output) if args.check else prepare(args.output,
        legacy_learning_root=args.legacy_learning_root, legacy_no_skill_root=args.legacy_no_skill_root)
    print(json.dumps({k: value[k] for k in ("record_hash", "evaluation_positions", "train_tasks", "selection_tasks")}
                     | {"status": "validated_not_launched" if args.check else value["status"], "model_calls": 0}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
