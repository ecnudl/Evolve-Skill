"""Prepare all 80 original Spreadsheet tasks, with new 65k model generation.

Execute from a NEW frozen common-source clone with only the reviewed Sheet v5
adapter overlays. A path/source-bound 17-control qualification must already
exist. This command reads metadata/assets but starts no model or container.
The old delivered workbooks, scores and unknowns are never imported or changed.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
from copy import deepcopy
from pathlib import Path

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
from skillopt.continual_eval.sheet_recalc_adapter import VERSION as SCORER
from skillopt.continual_eval.sheet_recalc_adapter import qualified_engine
from skillopt.validator_pilot.api import digest

VERSION = "long-spreadsheet-baseline-v1"
OVERLAYS = ("continual_eval/backends.py", "continual_eval/core.py", "continual_eval/runner.py",
            "continual_eval/sheet_recalc.py", "continual_eval/sheet_recalc_adapter.py")
GENERATION_FUNCTIONS = {"_code", "_response", "_xlsx_bytes", "_sheet_preview", "_native", "solve", "_runtime_limits"}
TRANSPORT = {"stream": True, "read_timeout_seconds": 300, "stream_wall_seconds": 1800,
             "initial_health_policy": "completed_response_v1"}
PROXY = "http://httpproxy-headless.kubebrain.svc.pjlab.local:3128"


def _sha(path):
    return hashlib.sha256(safe_path(path).read_bytes()).hexdigest()


def _generation(path):
    values = {n.name: ast.dump(n, include_attributes=False) for n in ast.parse(safe_path(path).read_text()).body
              if isinstance(n, ast.FunctionDef) and n.name in GENERATION_FUNCTIONS}
    require(set(values) == GENERATION_FUNCTIONS, "Original workbook generation implementation missing")
    return digest(values)


def _shared(common, approved_adapter):
    shared = read_json(common / "plan.json", sealed=True)
    validate_config(shared["config"])
    require(shared["version"] == "continual-eval-v2", "Common long-response plan required")
    overlay = {name: _sha(approved_adapter / "skillopt" / name) for name in OVERLAYS}
    require(source_identity() == {**shared["source_identity"], **overlay},
            "Use common frozen source/API plus ONLY reviewed Sheet overlays")
    require(runtime_identity() == shared["host_runtime"], "Common host dependencies changed")
    model = shared["config"]["model"]
    require(model == {"provider": "bigmodel", "name": "glm-5.3", "max_tokens": 65536,
                      "reasoning_effort": "low", "proxy": PROXY, "transport": TRANSPORT},
            "Unexpected common model/transport")
    service = read_json(common / "model_service.json", sealed=True)
    expected = {"provider": "BIGMODEL", "host": "open.bigmodel.cn", "path": "/api/paas/v4/chat/completions",
        "model": "glm-5.3", "reasoning_effort": "low", "proxy": PROXY, "stream": True,
        "stream_max_wall_seconds": 1800, "initial_health_policy": "completed_response_v1",
        "trust_env": False, "stream_transport": "async-whole-attempt-deadline-v1"}
    require(all(service.get(k) == v and type(service.get(k)) is type(v) for k, v in expected.items())
            and service.get("timeout_seconds", {}).get("read") == 300, "Common service differs")
    return shared, service, overlay


def prepare(legacy_root, common_run, approved_adapter_root, qualification_path, output):
    legacy, common, approved, qpath, root = map(safe_path,
        (legacy_root, common_run, approved_adapter_root, qualification_path, output))
    source_root = safe_path(Path(backends.__file__).parents[2])
    require(not root.exists() and not any(root.is_relative_to(p) or p.is_relative_to(root)
            for p in (legacy, common, approved, source_root, qpath.parent)), "New independent output required")
    old_path = legacy / "run/plan.json"
    old = read_json(old_path, sealed=True)
    shared, service, overlay = _shared(common, approved)
    require(old["version"] == "continual-eval-v1", "Original Sheet B protocol required")
    for plan in (old, shared):
        require(plan["config"]["partition"] == "development" and plan["repeats"] == 2
                and plan["config"]["methods"] == ["no_skill"] and plan["config"]["histories"] == ["h0"],
                "Only complete development No-Skill panels authorized")
    model = shared["config"]["model"]
    require(old["host_runtime"] == shared["host_runtime"]
            and all(old["config"]["model"][k] == model[k] for k in ("provider", "name", "reasoning_effort", "proxy")),
            "Original host/model differ beyond output/transport and new scorer")
    panel_path = safe_path(old["panels"]["spreadsheetbench"]["path"])
    panel = load_panel(panel_path)
    require(panel["benchmark"] == "spreadsheetbench" and panel["provenance"] == "natural"
            and panel_hash(panel) == old["panels"]["spreadsheetbench"]["panel_hash"]
            and len(panel["tasks"]) == len({t["family_id"] for t in panel["tasks"]}) == 80
            and all(t["partition"] == "development" for t in panel["tasks"])
            and data_readiness(panel)["status"] == "ready", "Full original 80-task assets/panel required")
    roster = [{"benchmark": "spreadsheetbench", **{k: t[k] for k in ("task_id", "family_id", "project_id", "partition")},
               "task_hash": digest(t)} for t in panel["tasks"]]
    require(roster == old["tasks"], "Historical complete roster changed")
    require(set(old["config"]["runtime"]) == {"spreadsheetbench"}, "Original Sheet-only runtime required")
    original_runtime = deepcopy(old["config"]["runtime"]["spreadsheetbench"])
    require(set(original_runtime) == {"image", "timeout_seconds", "memory_mb", "cpus", "spreadsheet_scorer"}
            and original_runtime["timeout_seconds"] == 300 and original_runtime["memory_mb"] == 4096
            and original_runtime["cpus"] == 1 and original_runtime["spreadsheet_scorer"] ==
            "spreadsheetbench-official-quote-and-string-cache-v1", "Original generation/native profile differs")
    q = read_json(qpath, sealed=True)
    runtime = {**original_runtime, "spreadsheet_scorer": SCORER, "recalculation": {
        "image": q["engine"]["image_id"], "timeout_seconds": q["engine"]["timeout_seconds"],
        "qualification_path": str(qpath), "qualification_sha256": _sha(qpath), "qualification_hash": q["record_hash"]}}
    engine, _ = qualified_engine(runtime)  # Checks all 17 controls/receipts/sources; NEVER runs Calc.
    require(engine.timeout == 120, "Keep the qualified 120-second recalculation profile")
    files = {str(p): _sha(p) for p in (old_path, common / "plan.json", common / "model_service.json", panel_path, qpath)}
    files.update({str(approved / "skillopt" / name): expected for name, expected in overlay.items()})
    files.update({str(qpath.parent / "receipts" / (c["name"] + ".json")):
                  _sha(qpath.parent / "receipts" / (c["name"] + ".json")) for c in q["controls"]})
    require({"continual_eval/backends.py", "continual_eval/native_worker.py"} <= set(old["source_identity"]),
            "Original generation source identity missing")
    for relative, expected in old["source_identity"].items():
        path = safe_path(legacy / "skillopt" / relative)
        require(path.is_relative_to(legacy / "skillopt") and _sha(path) == expected, "Historical source changed")
        files[str(path)] = expected
    generation_hash = _generation(legacy / "skillopt/continual_eval/backends.py")
    require(generation_hash == _generation(Path(backends.__file__))
            and old["source_identity"]["continual_eval/native_worker.py"] ==
            shared["source_identity"]["continual_eval/native_worker.py"], "Original generation/worker changed")
    config = {**deepcopy(shared["config"]), "panels": {b: str(root / "data/panel.json")
        if b == "spreadsheetbench" else None for b in BENCHMARKS},
        "runtime": {"spreadsheetbench": runtime}, "exposure_manifest": None}
    root.mkdir(parents=True, mode=0o700)
    write_json(root / "data/panel.json", panel)
    write_json(root / "config.json", config)
    plan = freeze_plan(config, root / "run")
    public_cases = sum(len(t["public"]["input_files"]) for t in panel["tasks"]) * 2
    value = seal({"version": VERSION, "status": "prepared_not_launched", "study_root": str(root),
        "common_run": str(common), "approved_adapter_root": str(approved), "original_files": files,
        "prepared_files": {str(p): _sha(p) for p in root.rglob("*.json")},
        "preparer_sha256": _sha(Path(__file__)), "plan_hash": plan["record_hash"],
        "common_plan_hash": shared["record_hash"], "common_service_hash": service["record_hash"],
        "panel_hash": panel_hash(panel), "reviewed_overlays": overlay, "generation_functions_hash": generation_hash,
        "original_generation_runtime": original_runtime, "qualification_hash": q["record_hash"],
        "qualification_controls": 17, "scorer_profile": SCORER,
        "tasks": 80, "families": 80, "repeats": 2, "positions": 160, "model": model,
        "model_calls": 0, "container_calls": 0, "max_generation_logical_calls": 160,
        "public_case_executions_max": public_cases, "recalculation_container_calls_max": public_cases * 2,
        "qualification_costs_are_separate": True, "workers": 2,
        "lock_requirement": "hold_common_native_and_s1_method_locks_across_generate_and_score",
        "evidence_kind": "natural_development_baseline_same_historically_exposed_panel_new_generation_and_scorer",
        "old_answers_imported": False, "old_scores_replaced": False, "unknowns_filtered": False,
        "causal_budget_effect_claimed": False, "excel_equivalence_proven": False,
        "skill_updated": False, "deployment_authorized": False})
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
    shared, service, overlay = _shared(safe_path(value["common_run"]), safe_path(value["approved_adapter_root"]))
    require(plan["record_hash"] == value["plan_hash"] and shared["record_hash"] == value["common_plan_hash"]
            and service["record_hash"] == value["common_service_hash"] and overlay == value["reviewed_overlays"],
            "Plan/service/overlay identity changed")
    return value


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    parser.add_argument("--legacy-root")
    parser.add_argument("--common-run")
    parser.add_argument("--approved-adapter-root")
    parser.add_argument("--qualification-path")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    require(args.check or all((args.legacy_root, args.common_run, args.approved_adapter_root, args.qualification_path)),
            "Legacy/common/approved adapter source and fresh qualification required")
    value = check(args.output) if args.check else prepare(args.legacy_root, args.common_run,
        args.approved_adapter_root, args.qualification_path, args.output)
    print(json.dumps({k: value[k] for k in ("record_hash", "plan_hash", "tasks", "positions", "model_calls", "container_calls")}
                     | {"status": "validated_not_launched" if args.check else value["status"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
