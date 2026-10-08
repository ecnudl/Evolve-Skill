"""Zero-call scope-routed deployment diagnostic for a frozen five-domain study.

A Skill's default authorized scope is the public deliverable contract type of
the training evidence behind its accepted updates; widening it needs new
behavioral evidence. Positions outside that scope are served by the clean
No-Skill policy, whose frozen observation is reused (not a new sample). The
pre-execution routing reads only the validated public contract schema, never
outcomes, hidden fields or evaluation scores. Routing rules fixed after seeing
forced results are a post-hoc diagnostic, not an independent final estimate.
"""
from __future__ import annotations

import argparse
import json
import os
from collections import Counter

from scripts.report_fivebench_generalization import aggregate, paired, row_index
from skillopt.coevolution_v5.core import seal
from skillopt.continual_eval.core import BENCHMARKS, read_json, require, safe_path, write_json
from skillopt.validator_pilot.api import digest

VERSION = "scope-routed-deployment-v1"
SCOPE_RULE = "default_scope_is_training_evidence_deliverable_type_v1"
SEQUENCES = {"fivebench-sequential-attempts-v1", "fivebench-sequential-attempts-v2",
             "fivebench-sequential-attempts-v3", "fivebench-sequential-attempts-v4"}
# One public deliverable contract per benchmark adapter, keyed by its exact public schema.
CONTRACTS = {"bigcodebench": ({"prompt", "entry_point"}, "python_function"),
             "spreadsheetbench": ({"instruction", "input_files", "answer_position"}, "workbook_program"),
             "searchqa": ({"question", "context"}, "short_answer"),
             "korbench": ({"rule", "question"}, "rule_answer"),
             "alfworld": ({"game_file"}, "environment_actions")}


def deliverable_type(benchmark, tasks):
    fields, kind = CONTRACTS[benchmark]
    require(tasks and all(set(task["public"]) == fields for task in tasks), "Unexpected public contract schema")
    return kind


ACTIONS = {"selected_update", "completed_no_update", "pending_carry_parent"}


def observed(rows):
    """Full observation identity: a reused policy must repeat statuses and evidence hashes."""
    row_index(rows)
    return {(r["task_id"], r["repeat"]): (r["family_id"], r["status"], r["record_hash"]) for r in rows}


def net(pair):
    return pair["positions"]["win"] - pair["positions"]["loss"]


def build(study, method="skillopt"):
    root = safe_path(study)
    protocol = read_json(root / "protocol.json", sealed=True)
    require(protocol["version"] in SEQUENCES and protocol["order"] == list(BENCHMARKS)
            and method in protocol["methods"], "Unsupported study or method")
    types, bases, excluded = {}, {}, {}
    for benchmark in BENCHMARKS:
        role = protocol["roles"][benchmark]
        types[benchmark] = deliverable_type(benchmark, read_json(role["path"])["tasks"])
        reference = protocol["references"][benchmark]
        bases[benchmark] = row_index(reference["rows"])
        require(len(bases[benchmark]) == reference["positions"], "Incomplete No-Skill reference")
        excluded[benchmark] = set(role["train"]) | set(role["selection"])
    scope, previous, parent_hash, stages = set(), "", None, []
    # The empty Skill is the No-Skill policy; any recurring Skill must reproduce its observation.
    seen = {(digest(""), t): observed(protocol["references"][t]["rows"]) for t in BENCHMARKS}
    for number, benchmark in enumerate(BENCHMARKS, 1):
        path = root / method / f"s{number}-{benchmark}" / "stage.json"
        if not path.is_file():
            break
        stage = read_json(path, sealed=True)
        require(stage["protocol_hash"] == protocol["record_hash"] and stage["method"] == method
                and stage["stage"] == number and stage["benchmark"] == benchmark
                and stage["parent_skill"] == previous and stage["parent_stage_hash"] == parent_hash,
                "Stage chain binding mismatch")
        require(stage["action"] in ACTIONS and (stage["action"] == "selected_update") == (stage["skill"] != previous),
                "Only an accepted update may change the Skill, and it must change it")
        if stage["action"] == "selected_update":
            scope.add(types[benchmark])
        for target in BENCHMARKS:
            result = stage["cells"][target]["result"]
            require(result["benchmark"] == target
                    and result["model_service"] == protocol["references"][target]["model_service"],
                    "Evaluation cell belongs to another domain or model service")
            current = observed(result["rows"])
            require(set(current) == set(bases[target]), "Incomplete or foreign evaluation cell")
            require(seen.setdefault((digest(stage["skill"]), target), current) == current,
                    "A recurring Skill changed its observation")
        previous, parent_hash = stage["skill"], stage["record_hash"]
        cells = {}
        for target in BENCHMARKS:
            base = bases[target]
            forced = stage["cells"][target]["result"]["rows"]
            in_scope = bool(stage["skill"]) and types[target] in scope
            routed = forced if in_scope else list(protocol["references"][target]["rows"])
            held = {k: r for k, r in base.items() if r["family_id"] not in excluded[target]}
            cells[target] = {
                "deliverable_type": types[target], "in_scope": in_scope,
                "routed_source": "forced_skill_observation" if in_scope else "reused_no_skill_reference",
                "forced": {"current": aggregate(forced, base), "paired": paired(forced, base)},
                "routed": {"current": aggregate(routed, base), "paired": paired(routed, base)},
                "learning_family_excluded": {
                    "available": bool(held),
                    "forced": paired([r for r in forced if r["family_id"] not in excluded[target]], held)
                    if held else None,
                    "routed": paired([r for r in routed if r["family_id"] not in excluded[target]], held)
                    if held else None}}
        out_of_scope = [c for c in cells.values() if not c["in_scope"]]
        summary = Counter({
            "forced_net_positions": sum(net(c["forced"]["paired"]) for c in cells.values()),
            "routed_net_positions": sum(net(c["routed"]["paired"]) for c in cells.values()),
            "forced_losses_avoided": sum(c["forced"]["paired"]["positions"]["loss"] for c in out_of_scope),
            "forced_wins_forgone": sum(c["forced"]["paired"]["positions"]["win"] for c in out_of_scope)})
        stages.append({"stage": number, "benchmark": benchmark, "action": stage["action"],
                       "skill_hash": digest(stage["skill"]), "skill_bytes": len(stage["skill"].encode()),
                       "authorized_deliverable_types": sorted(scope), "cells": cells, "summary": dict(summary)})
    return seal({"version": VERSION, "protocol_hash": protocol["record_hash"], "method": method,
                 "scope_rule": SCOPE_RULE, "deliverable_types": types, "stages": stages,
                 "model_api_calls": 0, "new_observations": 0, "post_hoc_diagnostic": True,
                 "independent_final": False, "deployment_authorized": False,
                 "data_scope": "previously_exposed_development_with_learning_overlap_not_final"})


def markdown(report):
    lines = [f"# 按适用范围部署诊断（{report['method']}）", "",
             f"规则：`{report['scope_rule']}`；0模型调用、0新观测；事后诊断，非独立final，无部署授权。", "",
             "| 阶段 | 授权交付类型 | 评测域 | 路由来源 | 强制：改善/退化/持平/未知 | 路由：改善/退化/持平/未知 |",
             "|---|---|---|---|---|---|"]
    for stage in report["stages"]:
        for target, cell in stage["cells"].items():
            f, r = cell["forced"]["paired"]["positions"], cell["routed"]["paired"]["positions"]
            lines.append(f"| S{stage['stage']} {stage['benchmark']} | {', '.join(stage['authorized_deliverable_types']) or '无'}"
                         f" | {target} | {cell['routed_source']} | {f['win']}/{f['loss']}/{f['tie']}/{f['unknown']}"
                         f" | {r['win']}/{r['loss']}/{r['tie']}/{r['unknown']} |")
    lines += ["", "| 阶段 | 强制净改善位置 | 路由净改善位置 | 避免的强制退化 | 放弃的强制改善 |", "|---|---:|---:|---:|---:|"]
    for stage in report["stages"]:
        s = stage["summary"]
        lines.append(f"| S{stage['stage']} | {s['forced_net_positions']} | {s['routed_net_positions']}"
                     f" | {s['forced_losses_avoided']} | {s['forced_wins_forgone']} |")
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--study", required=True)
    parser.add_argument("--method", default="skillopt", choices=("skillopt", "gepa"))
    parser.add_argument("--output", required=True, help="New directory outside the frozen study")
    args = parser.parse_args()
    study, output = safe_path(args.study), safe_path(args.output)
    # Compare existing ancestors by inode: case-insensitive volumes alias spellings.
    inside = any(parent.exists() and os.path.samefile(parent, study) for parent in (output, *output.parents))
    require(not output.exists() and not inside, "Use a new export directory outside the frozen study")
    report = build(study, args.method)
    output.mkdir(parents=True, mode=0o700)
    write_json(output / "report.json", report)
    (output / "report.md").write_text(markdown(report))
    print(json.dumps({"stages": len(report["stages"]), "record_hash": report["record_hash"]}))


if __name__ == "__main__":
    main()
