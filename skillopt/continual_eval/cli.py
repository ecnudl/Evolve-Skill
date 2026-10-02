"""Explicit prepare -> freeze -> generate -> host score -> report commands."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from . import backends, datasets
from .core import (
    BENCHMARKS,
    build_plan,
    freeze_plan,
    output_lock,
    read_json,
    register_checkpoint,
    safe_path,
    validate_config,
    write_json,
)
from .runner import close_interrupted, generate, report, score_checkpoint


def readiness(config):
    config = validate_config(config)
    result = {}
    for benchmark in config["order"]:
        path = config["panels"][benchmark]
        if path is None or not Path(path).is_file():
            data = {"status": "missing", "reason": "normalized_panel_not_prepared"}
        else:
            data = datasets.readiness(datasets.load_panel(path))
        runtime = backends.readiness(benchmark, config["runtime"].get(benchmark, {}))
        result[benchmark] = {"data": data, "runtime": runtime,
                             "ready": data["status"] == "ready" and runtime["status"] == "ready"}
    plan = build_plan(config)
    return {"version": config["version"], "benchmarks": result,
            "all_five_ready": all(r["ready"] for r in result.values()),
            "protocol_complete": plan["protocol_complete"], "model_calls": 0,
            "note": "Readiness is not method-effect evidence; model credentials are not probed."}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    prepare = sub.add_parser("prepare", help="Import a local dataset, without model calls or code execution")
    prepare.add_argument("--benchmark", choices=BENCHMARKS, required=True)
    prepare.add_argument("--source", required=True)
    prepare.add_argument("--revision", required=True)
    prepare.add_argument("--partition", choices=("development", "verifier_calibration", "skill_confirmation", "final"),
                         default="development")
    prepare.add_argument("--output", required=True)
    prepare.add_argument("--family-map")
    prepare.add_argument("--rules", help="KOR official rule file")
    prepare.add_argument("--category", help="KOR category")
    prepare.add_argument("--variant", choices=("instruct", "complete"), default="instruct")
    prepare.add_argument("--data-root", help="Spreadsheet/ALFWorld asset root")
    for command in ("check", "freeze"):
        p = sub.add_parser(command)
        p.add_argument("--config", required=True)
        if command == "freeze":
            p.add_argument("--output", required=True)
        else:
            p.add_argument("--output", help="Optional immutable readiness report")
    cp = sub.add_parser("checkpoint", help="Register externally produced, frozen Skill; does not evolve or authorize it")
    cp.add_argument("--run", required=True)
    cp.add_argument("--method", required=True)
    cp.add_argument("--history", default="h0")
    cp.add_argument("--stage", type=int, required=True)
    cp.add_argument("--skill", help="UTF-8 Skill file; omit for an empty baseline")
    cp.add_argument("--provenance", required=True)
    for command in ("generate", "score"):
        p = sub.add_parser(command)
        p.add_argument("--run", required=True)
        p.add_argument("--method", default="no_skill")
        p.add_argument("--history", default="h0")
        p.add_argument("--stage", type=int, default=0)
        p.add_argument("--benchmark", choices=BENCHMARKS, required=True)
        if command == "generate":
            p.add_argument("--repo", default=str(Path(__file__).resolve().parents[2]))
            p.add_argument("--workers", type=int, default=1)
    for command in ("report", "close-interrupted"):
        p = sub.add_parser(command)
        p.add_argument("--run", required=True)
        if command == "close-interrupted":
            p.add_argument("--position", required=True)
    p = sub.add_parser("smoke", help="Offline engineering fixture; zero paid calls, no generated code execution")
    p.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    if args.command == "prepare":
        kw = {"partition": args.partition, "revision": args.revision,
              "family_map": read_json(args.family_map) if args.family_map else None}
        if args.benchmark == "searchqa":
            value = datasets.import_searchqa(args.source, **kw)
        elif args.benchmark == "bigcodebench":
            value = datasets.import_bigcodebench(args.source, split=args.variant, **kw)
        elif args.benchmark == "korbench":
            if not args.rules or not args.category:
                parser.error("KOR requires --rules and --category")
            if args.family_map:
                parser.error("KOR families are fixed by category/rule; --family-map is unsupported")
            value = datasets.import_korbench(args.source, args.rules, category=args.category,
                                             partition=args.partition, revision=args.revision)
        elif args.benchmark == "spreadsheetbench":
            if not args.data_root:
                parser.error("Spreadsheet requires --data-root")
            value = datasets.import_spreadsheetbench(args.source, data_root=args.data_root, **kw)
        else:
            if not args.data_root:
                parser.error("ALFWorld requires --data-root")
            value = datasets.import_alfworld(args.source, data_root=args.data_root, **kw)
        write_json(args.output, value)
        result = datasets.readiness(datasets.load_panel(args.output))
    elif args.command == "check":
        result = readiness(read_json(args.config))
        if args.output:
            write_json(args.output, result)
    elif args.command == "freeze":
        value = freeze_plan(read_json(args.config), args.output)
        result = {"plan_hash": value["record_hash"], "tasks": len(value["tasks"]),
                  "protocol_complete": value["protocol_complete"], "evidence_kind": value["evidence_kind"]}
    elif args.command == "checkpoint":
        text = safe_path(args.skill).read_text(encoding="utf-8") if args.skill else ""
        with output_lock(args.run):
            value = register_checkpoint(args.run, args.method, args.history, args.stage, text, provenance=args.provenance)
        result = {"checkpoint_hash": value["record_hash"], "stage": args.stage, "deployment_authorized": False}
    elif args.command == "generate":
        result = generate(args.run, method=args.method, history=args.history, stage=args.stage,
                          benchmark=args.benchmark, repo=args.repo, workers=args.workers)
    elif args.command == "score":
        result = score_checkpoint(args.run, method=args.method, history=args.history, stage=args.stage,
                                  benchmark=args.benchmark)
    elif args.command == "close-interrupted":
        result = close_interrupted(args.run, args.position)
    elif args.command == "smoke":
        from .fixtures import smoke
        result = smoke(args.output)
    else:
        result = report(args.run)
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
