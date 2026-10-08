"""Zero-call report of learning-v8 stage redos (``run_fivebench_g_stage.py`` outputs).

Reads each prepared stage directory's sealed ``stage.json``, ``learned.json`` and, when an
accepted update was tested, ``summary.json``; prints one Markdown row per stage (method,
domain, parent, train/val sizes, every gate step, the deployed outcome and the paired test
result against the recorded No-Skill cell) and optionally exports one sealed JSON record.
It verifies the records' mutual bindings and never calls a model or touches a run.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from skillopt.coevolution_v5.core import seal
from skillopt.continual_eval.core import read_json, require, safe_path, write_json

VERSION = "fivebench-g-stages-report-v1"


def load_stage(path):
    root = safe_path(path)
    stage = read_json(root / "stage.json", sealed=True)
    row = {"directory": str(root), "stage_hash": stage["record_hash"], "method": stage.get("method", "skillopt"),
           "benchmark": stage["benchmark"], "parent": stage["parent"], "train_tasks": stage["train_tasks"],
           "selection_tasks": stage["selection_tasks"], "selection_families": stage["selection_families"],
           "learning_version": stage["learning_version"], "status": "prepared"}
    learned_path = root / "learned.json"
    if not learned_path.exists():
        return row
    learned = read_json(learned_path, sealed=True)
    require(learned["stage_hash"] == stage["record_hash"], "learned.json does not belong to this stage")
    row.update(status=learned["status"], action=learned["action"], reason=learned["reason"],
               steps=learned["steps"], accepted_steps=learned.get("accepted_steps"),
               skill_bytes=learned["skill_bytes"], skill_sha256=learned["skill_sha256"],
               learning_calls=learned["costs"]["logical_calls"],
               learning_tokens=learned["costs"]["reported_tokens_known_subtotal"],
               **{k: learned[k] for k in ("official_best_rejected", "final_margin") if k in learned})
    if learned.get("verifier_steps") is not None:  # v10 main method: the verifier's per-step summary
        row["verifier"] = [{k: step.get(k) for k in ("step", "policy_status", "policy_changed", "rows", "rows_with_probes",
                                                      "probes_executed", "probes_failed", "probes_error", "research_rows",
                                                      "detections", "false_rejections", "false_rejection_rate",
                                                      "authorized", "reports_with_feedback", "citations")}
                           for step in learned["verifier_steps"]]
        row["verifier_calls"] = learned["costs"].get("verifier_calls")
        row["verifier_policy_status"] = learned.get("verifier_policy_status")
    tests, replicates = {}, {}
    for summary_path in sorted(root.glob("summary*.json")):
        summary = read_json(summary_path, sealed=True)
        require(summary["stage_hash"] == stage["record_hash"] and summary["skill_sha256"] == learned["skill_sha256"],
                f"{summary_path.name} does not belong to this stage's deployed Skill")
        cell = {k: summary[k] for k in (
            "test_positions", "test_counts", "no_skill_counts", "wins_vs_no_skill", "losses_vs_no_skill",
            "net_vs_no_skill", "no_skill_unknown", "new_unknown", "jointly_known", "families_improving",
            "families_regressing")}
        cell["calls"] = summary["test_costs"]["logical_calls"]
        if "replicate" in summary:  # an additional independent cell of the same Skill: never merged with the primary
            key = f"{summary['benchmark']}#r{summary['replicate']}"
            require(key not in replicates, "Duplicate replicate cell")
            replicates[key] = cell
        else:
            require(summary["benchmark"] not in tests, "Duplicate primary test cell")
            tests[summary["benchmark"]] = cell
    if tests:
        row["tests"] = tests  # primary cells by test domain
        row["test"] = tests.get(stage["benchmark"])
    if replicates:
        row["replicates"] = replicates  # "<domain>#r<k>": independent re-measurements of the deployed Skill
    return row


def _steps(row):
    parts = []
    for s in row.get("steps", []):
        action = s.get("gate_action") or "?"
        if s.get("net_wins") is not None and s.get("required_net_wins") is not None:
            parts.append(f"{action} {s['wins']}胜/{s['losses']}负（需净胜{s['required_net_wins']}）")
        elif s.get("first_pass") is not None:  # v9: screen on the first pass, decision on the fresh confirmation pass
            first, second = s["first_pass"], s.get("confirmation_pass")
            text = (f"{action} 筛选{first['wins']}胜/{first['losses']}负（族{first['families_improving']}升/"
                    f"{first['families_regressing']}降，p={first['family_p_value']:.3g}）")
            if second:
                text += (f"；确认{second['wins']}胜/{second['losses']}负（族{second['families_improving']}升/"
                         f"{second['families_regressing']}降，p={second['family_p_value']:.3g}，"
                         f"阈值{s['accept_alpha_effective']:.3g}）")
            parts.append(text)
        else:
            parts.append(action)
    return "；".join(parts) or "—"


def markdown(rows):
    lines = ["| 方法 | 域 | 父Skill | 训练/val | 各轮门控 | 结果 | test（相对No-Skill） |", "|---|---|---|---|---|---|---|"]
    for row in rows:
        outcome = row["status"] if row["status"] == "prepared" else f"{row['action']}（{row.get('skill_bytes')}字节）"
        test = "—"
        if row.get("tests"):
            cells = []
            for domain, t in row["tests"].items():
                passed = t["test_counts"].get("pass", 0)
                base = t["no_skill_counts"].get("pass", 0)
                cells.append(f"{domain}: {passed}/{t['test_positions']}（No-Skill {base}；{t['wins_vs_no_skill']}胜/"
                             f"{t['losses_vs_no_skill']}负，净{t['net_vs_no_skill']:+d}；族+{t['families_improving']}/"
                             f"−{t['families_regressing']}" + (f"；U{t['new_unknown']}" if t["new_unknown"] else "") + "）")
            test = "<br>".join(cells)
        elif row.get("action") == "selected_update":
            test = "待评测"
        if row.get("replicates"):
            reps = []
            for key, t in row["replicates"].items():
                reps.append(f"{key}: {t['test_counts'].get('pass', 0)}/{t['test_positions']}（对记录的No-Skill格 "
                            f"{t['wins_vs_no_skill']}胜/{t['losses_vs_no_skill']}负）")
            test = (test + "<br>" if test not in {"—", ""} else "") + "重复测量 " + "；".join(reps)
        elif row.get("action") in {"completed_no_update", "pending_carry_parent"}:
            test = "父Skill已有记录"
        lines.append(f"| {row['method']} | {row['benchmark']} | {row['parent']} | {row['train_tasks']}/{row['selection_tasks']} "
                     f"| {_steps(row)} | {outcome} | {test} |")
    return "\n".join(lines)


def chain_table(rows, domains=("bigcodebench", "searchqa", "korbench")):
    """Stage-by-stage table of one chain: each row deploys its own tested Skill or, without an
    accepted update, inherits the cells of the stage it chained from (``g:`` parent); No-Skill
    counts come from the recorded No-Skill cells the stages were paired with."""
    by_dir = {row["directory"]: row for row in rows}
    lines = ["| 阶段 | " + " | ".join(domains) + " |", "|---|" + "---|" * len(domains)]
    base = {}
    for row in rows:
        for domain, t in row.get("tests", {}).items():
            base[domain] = (t["no_skill_counts"].get("pass", 0), t["test_positions"])
    lines.append("| 初始 No-Skill | " + " | ".join(f"{base[d][0]}/{base[d][1]}" if d in base else "—" for d in domains) + " |")

    def cells(row):
        if row.get("action") == "selected_update":
            return row.get("tests", {}), row["benchmark"]
        parent = row["parent"]
        if parent.startswith("g:") and parent[2:] in by_dir:
            return cells(by_dir[parent[2:]])[0], None
        return {}, None  # parent is No-Skill or an F Skill: nothing of this chain's own to show

    for number, row in enumerate(rows, 1):
        tests, _ = cells(row)
        out = []
        for d in domains:
            t = tests.get(d)
            if t is None:
                out.append(f"{base[d][0]}/{base[d][1]}（沿用No-Skill）" if d in base and row["parent"] == "none" else "—")
                continue
            tag = "" if row.get("action") == "selected_update" else "（沿用上一阶段）"
            out.append(f"{t['test_counts'].get('pass', 0)}/{t['test_positions']}（{t['wins_vs_no_skill']}/{t['losses_vs_no_skill']}"
                       + (f"，U{t['new_unknown']}" if t["new_unknown"] else "") + f"）{tag}")
        action = {"selected_update": "更新", "completed_no_update": "无更新", "pending_carry_parent": "Pending"}.get(
            row.get("action"), row["status"])
        lines.append(f"| S{number} 在{row['benchmark']}上进化（{action}） | " + " | ".join(out) + " |")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stages", nargs="+", required=True)
    parser.add_argument("--export", help="New JSON file for the sealed combined record")
    parser.add_argument("--chain", action="store_true", help="also print the stage-by-stage chain table (stages in order)")
    args = parser.parse_args()
    rows = [load_stage(p) for p in args.stages]
    print(markdown(rows))
    if args.chain:
        print()
        print(chain_table(rows))
    if args.export:
        out = Path(args.export)
        require(not out.exists(), "Use a new export file")
        write_json(out, seal({"version": VERSION, "stages": rows, "model_calls": 0,
                              "note": "single-domain learning-v8 stage redos on study F's frozen references; one test "
                                      "cell per accepted update, paired with the recorded No-Skill test cell; not a "
                                      "sequential study, not an interference measurement"}))
        print(json.dumps({"exported": str(out), "stages": len(rows)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
