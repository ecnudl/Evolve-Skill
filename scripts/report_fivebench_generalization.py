"""Read-only five-domain progress/comparison; export only public aggregate data.

Snapshots are descriptive development evidence, not independent final claims.
No solver output, Skill text, prompts, task content, API cache, or key is exported.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import tempfile
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone

from skillopt.coevolution_v5.core import seal
from skillopt.continual_eval.core import BENCHMARKS, read_json, require, safe_path, write_json
from skillopt.validator_pilot.api import digest

STATUSES = {"pass", "fail", "unknown"}
# Learning ledgers report reported_tokens_known_subtotal; evaluation runs report
# reported_tokens. Both are kept, never summed into one another or zero-filled.
COST_KEYS = {"logical_calls", "terminal_calls", "unclosed_calls", "http_attempts",
             "http_attempts_known_subtotal", "http_attempts_total", "reported_tokens_known_subtotal",
             "reported_tokens", "missing_usage_calls", "missing_attempt_usage", "usage_complete",
             "retry_inclusive_usage_known", "reflection_calls", "solver_calls",
             "unknown_cost_attempts", "delivered_without_usage", "blocking_usage_gap",
             "receipt_attempt_limit_exceeded", "unknown_cost_attempt_cap_exceeded"}


def costs(value):
    return {k: v for k, v in value.items() if k in COST_KEYS and (v is None or type(v) in {int, bool})}


def row_index(rows):
    result = {}
    for row in rows:
        require(type(row.get("task_id")) is str and type(row.get("family_id")) is str
                and type(row.get("repeat")) is int and row["repeat"] >= 0
                and row.get("status") in STATUSES, "Invalid score metadata")
        key = (row["task_id"], row["repeat"])
        require(key not in result, "Duplicate task/repeat score")
        result[key] = {k: row[k] for k in ("task_id", "family_id", "repeat", "status")}
    return result


def aggregate(rows, expected):
    observed = row_index(rows)
    require(set(observed) <= set(expected)
            and all(row["family_id"] == expected[key]["family_id"] for key, row in observed.items()),
            "Compared score identities differ from No-Skill")
    n = len(expected)
    count = Counter(r["status"] for r in observed.values())
    return {"positions": n, "scored": len(observed), "unscored": n - len(observed),
            "tasks": len({k[0] for k in expected}),
            "families": len({r["family_id"] for r in expected.values()}),
            "counts": {s: count[s] for s in ("pass", "fail", "unknown")},
            "confirmed_pass_rate": count["pass"] / n if n else None,
            "known_coverage": (count["pass"] + count["fail"]) / n if n else None,
            "success_bounds": [count["pass"] / n, (n - count["fail"]) / n] if n else None}


def paired(rows, baseline):
    current = row_index(rows)
    aggregate(rows, baseline)  # Enforce exactly the same identity space.
    count = Counter()
    family = defaultdict(Counter)
    win_tasks, loss_tasks = set(), set()
    for key, base in baseline.items():
        item = current.get(key)
        if item is None:
            label = "unscored"
        elif "unknown" in {base["status"], item["status"]}:
            label = "unknown"
        elif base["status"] == item["status"]:
            label = "tie"
        elif item["status"] == "pass":
            label = "win"
            win_tasks.add(key[0])
        else:
            label = "loss"
            loss_tasks.add(key[0])
        count[label] += 1
        family[base["family_id"]][label] += 1
    directions = Counter()
    for values in family.values():
        if values["unknown"] or values["unscored"]:
            directions["uncertain"] += 1
        else:
            directions["win" if values["win"] > values["loss"] else
                       "loss" if values["loss"] > values["win"] else "tie"] += 1
    return {"positions": {k: count[k] for k in ("win", "loss", "tie", "unknown", "unscored")},
            "tasks_with_win": len(win_tasks), "tasks_with_loss": len(loss_tasks),
            "families_with_win": sum(bool(x["win"]) for x in family.values()),
            "families_with_loss": sum(bool(x["loss"]) for x in family.values()),
            "family_net_direction": {k: directions[k] for k in ("win", "loss", "tie", "uncertain")},
            "significance_claimed": False}


def comparison(rows, reference, role):
    base = row_index(reference["rows"])
    require(len(base) == reference["positions"], "Incomplete baseline reference")
    baseline = aggregate(reference["rows"], base)
    require({k: v for k, v in baseline["counts"].items() if v} ==
            {k: v for k, v in reference["counts"].items() if v}, "Baseline count mismatch")
    current = aggregate(rows, base)
    excluded = set(role["train"]) | set(role["selection"])
    held = {k: r for k, r in base.items() if r["family_id"] not in excluded}
    held_rows = [r for r in rows if r["family_id"] not in excluded]
    return {"no_skill": baseline, "current": current, "paired": paired(rows, base),
            "confirmed_pass_delta": current["confirmed_pass_rate"] - baseline["confirmed_pass_rate"]
              if current["unscored"] == 0 else None,
            "learning_family_excluded": {"available": bool(held),
                "scope": "exclude_all_planned_train_and_selection_families_not_independent_final",
                "no_skill": aggregate(list(held.values()), held),
                "current": aggregate(held_rows, held), "paired": paired(held_rows, held)}}


def build_report(study, method="skillopt"):
    root = safe_path(study)
    protocol = read_json(root / "protocol.json", sealed=True)
    require(protocol["order"] == list(BENCHMARKS) and method in protocol["methods"], "Unsupported study/method")
    require(protocol["version"] in {"fivebench-sequential-attempts-v1", "fivebench-sequential-attempts-v2",
                                    "fivebench-sequential-attempts-v3", "fivebench-sequential-attempts-v4"},
            "Unsupported study version")
    stages, evaluation_costs = [], {}
    for number, benchmark in enumerate(BENCHMARKS, 1):
        directory = root / method / f"s{number}-{benchmark}"
        stage_path, decision_path = directory / "stage.json", directory / "decision.json"
        stage = read_json(stage_path, sealed=True) if stage_path.exists() else None
        decision = stage or (read_json(decision_path, sealed=True) if decision_path.exists() else None)
        if decision:
            require(decision["protocol_hash"] == protocol["record_hash"]
                    and decision["method"] == method and decision["stage"] == number
                    and decision["benchmark"] == benchmark, "Stage/protocol identity mismatch")
        result_path = directory / "learning/result.json"
        result = read_json(result_path, sealed=True) if result_path.exists() else None
        if result:
            require(result["status"] in {"completed", "pending"}, "Unexpected learning status")
        if result and decision:
            require(result["record_hash"] == decision["learning_result_hash"], "Learning result mismatch")
            require(result["candidate_skill"] == decision["skill"], "Learning/decision policy mismatch")
        if stage:
            require(result is not None and set(stage["cells"]) == set(BENCHMARKS)
                    and stage["learning_completed"] is (result["status"] == "completed"),
                    "Closed stage is missing learning or evaluation evidence")
        row = {"stage": number, "source": benchmark,
               "state": "stage_closed" if stage else "evaluation_incomplete" if decision else
                        "learning_terminal" if result else "started_or_interrupted" if directory.exists() else "not_started",
               "learning_status": result["status"] if result else "no_terminal_record",
               "learning_completed": bool(result and result["status"] == "completed"),
               "learning_costs": costs(result["costs"]) if result else None,
               "learning_terminal_calls_observed": len(list((directory / "learning/calls").glob("*.json"))),
               "action": decision["action"] if decision else None,
               "empty_skill": decision["skill"] == "" if decision else None,
               "skill_hash": digest(decision["skill"]) if decision else None,
               "learning_result_hash": result["record_hash"] if result else None,
               "cells": {}}
        for target in BENCHMARKS:
            reference = protocol["references"][target]
            cell = stage["cells"].get(target) if stage else None
            path = directory / f"evaluation-{target}.json"
            evaluated = cell["result"] if cell else read_json(path, sealed=True) if path.exists() else None
            if evaluated:
                require(evaluated["benchmark"] == target, "Evaluation target mismatch")
                require(evaluated["model_service"] == reference["model_service"], "Evaluation service mismatch")
                scores = evaluated["rows"]
                require(len(scores) == evaluated["positions"] == reference["positions"], "Incomplete terminal cell")
            else:
                # A running worker has no terminal report yet. Scores already
                # written are observed partial records, not process liveness.
                scores = [read_json(p, sealed=True) for p in sorted(
                    (directory / "evaluations" / target / "host_only/scores").glob("*.json"))]
            item = comparison(scores, reference, protocol["roles"][target])
            if evaluated:
                require({k: v for k, v in item["current"]["counts"].items() if v} ==
                        {k: v for k, v in evaluated["counts"].items() if v}, "Evaluation count mismatch")
            reused = cell["reused"] if cell else None
            item.update(terminal=evaluated is not None, reused=reused,
                        independent_new_observation=cell["independent_new_observation"] if cell else None,
                        evidence_hash=evaluated["record_hash"] if evaluated else None,
                        referenced_costs=costs(evaluated["costs"]) if evaluated else None,
                        new_costs={"logical_calls": 0} if reused else costs(evaluated["costs"]) if evaluated else None)
            row["cells"][target] = item
            if evaluated and not reused:
                evaluation_costs[evaluated["record_hash"]] = item["new_costs"]
        stages.append(row)
    return seal({"version": "fivebench-safe-progress-report-v1", "created_utc": datetime.now(timezone.utc).isoformat(),
                 "protocol_hash": protocol["record_hash"], "method": method,
                 "model": {k: protocol["model"][k] for k in ("provider", "name", "max_tokens", "reasoning_effort")},
                 "evidence_kind": "engineering_fixture" if protocol["model"]["provider"] == "fixture"
                    else "real_model_development_progress_snapshot",
                 "evaluation_policy": protocol.get("evaluation_policy", "original_frozen_primary_scoring"),
                 "data_scope": "previously_exposed_development_not_independent_final",
                 "completed_learning_stages": sum(r["learning_completed"] for r in stages),
                 "closed_all_domain_stages": sum(r["state"] == "stage_closed" for r in stages),
                 "evaluation_cost_records_deduplicated": list(evaluation_costs.values()),
                 "stages": stages, "deployment_authorized": False, "causal_generalization_claimed": False})


def markdown(report):
    lines = ["# 五域 Baseline 进度与比较", "",
             f"方法：{report['method']}；模型：{report['model']['name']}；快照：{report['created_utc']}。", "",
             f"完整学习 {report['completed_learning_stages']}/5；全域评测闭合 {report['closed_all_domain_stages']}/5。",
             "这是已接触的开发数据；重复执行不等于新增独立任务，不能宣称独立最终泛化效果。", "",
             "## 确认正确数 / 全部分母", "",
             "U=已评分但未知；待=尚无评分。分母始终保留未知及未完成位置。", "",
             "| 阶段 | 学习状态 | " + " | ".join(BENCHMARKS) + " |",
             "|---|---|" + "---|" * len(BENCHMARKS)]
    def cell_text(value):
        if value["unscored"] == value["positions"] and value["positions"]:
            return f"未评测（0/{value['positions']}已评分）"
        return f"{value['counts']['pass']}/{value['positions']}（U{value['counts']['unknown']}，待{value['unscored']}）"
    lines.append("| No-Skill | 固定基线 | " + " | ".join(
        cell_text(report["stages"][0]["cells"][b]["no_skill"]) for b in BENCHMARKS) + " |")
    for row in report["stages"]:
        cells = [cell_text(row["cells"][b]["current"]) + ("〔复用〕" if row["cells"][b]["reused"] else "")
                 for b in BENCHMARKS]
        lines.append(f"| S{row['stage']} {row['source']} | {row['learning_status']} / {row['state']} | " +
                     " | ".join(cells) + " |")
    lines += ["", "〔复用〕指引用相同策略的既有观测，不是新的独立实验；空 Skill 复用不能说明成功学到了泛化能力。",
              "", "## 相对 No-Skill 的配对差异", "",
              "| 阶段 | 评测域 | 改善 / 退化 / 持平 / 未知 / 待 | 有改善任务族 / 有退化任务族 | 学习集合外族：P/N（U；待） |",
              "|---|---|---|---|---|"]
    for row in report["stages"]:
        for benchmark, item in row["cells"].items():
            if not item["current"]["scored"]:
                continue
            pair = item["paired"]
            counts = " / ".join(str(pair["positions"][k]) for k in ("win", "loss", "tie", "unknown", "unscored"))
            held = item["learning_family_excluded"]
            lines.append(f"| S{row['stage']} | {benchmark} | {counts} | "
                         f"{pair['families_with_win']} / {pair['families_with_loss']} | "
                         f"{cell_text(held['current']) if held['available'] else '无（全部进入计划学习集合）'} |")
    lines += ["", "学习集合外按所有计划 train/selection 任务族排除，不代表从未接触或项目级独立最终测试。",
              "这是只读进度快照，不替代运行器的完整源码、环境及回执链复核。",
              "完整 JSON 保留逐阶段成本、unknown/覆盖率、任务族方向与证据哈希；运行中成本缺失记为 null，不记零。", ""]
    return "\n".join(lines)


def _export(destination, result):
    """Create a new export only; existing reports are never overwritten."""
    destination = safe_path(destination)
    destination.mkdir(parents=True, exist_ok=False, mode=0o700)
    write_json(destination / "report.json", result)
    with (destination / "report.md").open("x", encoding="utf-8") as handle:
        handle.write(markdown(result))


def _terminal_signature(root, method):
    paths = [root / "protocol.json", root / method / "final.json"]
    for number, benchmark in enumerate(BENCHMARKS, 1):
        stage = root / method / f"s{number}-{benchmark}"
        paths += [stage / name for name in ("learning/result.json", "decision.json", "stage.json")]
        paths += [stage / f"evaluation-{target}.json" for target in BENCHMARKS]
    # Files are atomic immutable records. Only host summaries are read; no API
    # cache, prompts or generated artifacts are scanned for progress detection.
    return tuple((str(path.relative_to(root)), hashlib.sha256(safe_path(path).read_bytes()).hexdigest())
                 for path in paths if path.is_file())


def _latest_index(destination, value):
    # Only this explicit operational pointer is mutable. The destination is a
    # newly created private export dir, outside all frozen input directories;
    # individual snapshot data and final watch-result stay immutable.
    target = safe_path(destination / "latest.json")
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=destination,
                                         prefix=".latest-", delete=False) as handle:
            temporary = handle.name
            json.dump(seal(value), handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
        temporary = None
    finally:
        if temporary is not None:
            os.unlink(temporary)


def _final_observed(root, method, report):
    path = root / method / "final.json"
    if not path.exists():
        return False
    final = read_json(path, sealed=True)
    stages = [read_json(root / method / f"s{i}-{b}/stage.json", sealed=True)["record_hash"]
              for i, b in enumerate(BENCHMARKS, 1)]
    require(final["protocol_hash"] == report["protocol_hash"] and final["method"] == method
            and final["status"] in {"completed", "attempts_finished_with_pending"}
            and final["attempted_stages"] == report["closed_all_domain_stages"] == 5
            and final["completed_learning_stages"] == report["completed_learning_stages"]
            and final["stage_hashes"] == stages, "Final summary does not match the observed stages")
    return True


def watch(study, method, output, *, interval=60, hours=12, _clock=None, _sleep=None):
    """Finite read-only watcher; every export lives outside the frozen study.

    Terminal-file changes trigger a snapshot, plus a 15-minute progress snapshot
    for long generations with no terminal file yet. No task is submitted/retried.
    An interrupted watcher is not resumed into an existing export directory.
    """
    require(type(interval) is int and 1 <= interval <= 60, "Watch interval must be 1..60 seconds")
    require(type(hours) in {int, float} and math.isfinite(hours) and 0 < hours <= 24,
            "Watch duration must be positive and at most 24 hours")
    root, destination = safe_path(study), safe_path(output)
    require(not destination.is_relative_to(root), "Export must be outside the frozen study")
    require(not destination.exists(), "Use a new report export directory")
    # Validate before making an output directory or entering the wait loop.
    initial = build_report(root, method)
    destination.mkdir(parents=True, exist_ok=False, mode=0o700)
    clock, sleep = _clock or time.monotonic, _sleep or time.sleep
    deadline, last_export = clock() + hours * 3600, None
    last_signature, count = None, 0
    while True:
        now = clock()
        signature = _terminal_signature(root, method)
        due = now >= deadline
        terminal = (root / method / "final.json").exists()
        if (signature != last_signature or last_export is None or now - last_export >= 900
                or terminal or due):
            result = build_report(root, method)
            require(result["protocol_hash"] == initial["protocol_hash"], "Watched protocol changed")
            finished = _final_observed(root, method, result)
            _export(destination / f"snapshot-{count:04d}", result)
            count += 1
            _latest_index(destination, {"version": "fivebench-report-latest-v1",
                                        "protocol_hash": result["protocol_hash"],
                                        "snapshot": f"snapshot-{count - 1:04d}",
                                        "report_hash": result["record_hash"], "snapshots": count})
            last_signature, last_export = signature, now
            print({"snapshot": count, "report_hash": result["record_hash"],
                   "completed_learning_stages": result["completed_learning_stages"],
                   "closed_all_domain_stages": result["closed_all_domain_stages"]}, flush=True)
            if finished or due:
                summary = seal({"version": "fivebench-read-only-watch-v1", "protocol_hash": result["protocol_hash"],
                                "method": method, "snapshots": count,
                                "status": "final_observed" if finished else "watch_deadline_reached",
                                "latest_snapshot": f"snapshot-{count - 1:04d}",
                                "latest_report_hash": result["record_hash"], "model_calls": 0,
                                "study_modified": False})
                write_json(destination / "watch-result.json", summary)
                return summary
        remaining = deadline - clock()
        if remaining > 0:
            sleep(min(interval, remaining))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--study", required=True)
    parser.add_argument("--method", default="skillopt", choices=("skillopt", "gepa"))
    parser.add_argument("--output", required=True, help="New export directory outside the frozen study")
    parser.add_argument("--watch", action="store_true", help="Watch read-only; stop on final.json or a finite deadline")
    parser.add_argument("--interval", type=int, default=60, help="Watch poll interval, 1..60 seconds")
    parser.add_argument("--hours", type=float, default=12, help="Watch time limit, positive and <=24 hours")
    args = parser.parse_args()
    root, destination = safe_path(args.study), safe_path(args.output)
    require(not destination.is_relative_to(root), "Export must be outside the frozen study")
    require(not destination.exists(), "Use a new report export directory")
    if args.watch:
        summary = watch(root, args.method, destination, interval=args.interval, hours=args.hours)
        print({k: summary[k] for k in ("status", "snapshots", "latest_snapshot")})
        return
    result = build_report(root, args.method)
    _export(destination, result)
    print({"report_hash": result["record_hash"], "completed_learning_stages": result["completed_learning_stages"],
           "closed_all_domain_stages": result["closed_all_domain_stages"]})


if __name__ == "__main__":
    main()
