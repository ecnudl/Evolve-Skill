"""Publish immutable V14 results after locked zero-API, zero-execution replay."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from scripts.coevolution_v14 import completed_replay, study_module, tree  # noqa: E402
from scripts.launch_coevolution_v14 import report_target  # noqa: E402
from skillopt.coevolution_v5.core import seal  # noqa: E402
from skillopt.scope_evolution_v2.source_data import write_immutable_text  # noqa: E402

DOMAINS = ("coding", "spreadsheet", "rule_reasoning")
LABELS = {"no_skill": "NoSkill", "independent": "Independent", "constrained": "Constrained"}


def _pct(value):
    return "不可评" if value is None else f"{100 * value:.2f}%"


def _pp(value):
    return f"{100 * value:+.2f} pp"


def _ci(measure):
    return f"[{_pp(measure['ci95']['low'])}, {_pp(measure['ci95']['high'])}]"


def _learning_rows(root, protocol, result):
    module = study_module()
    expected = {f"h{h}-r{r}-{arm}" for h in range(protocol["histories"])
                for r in range(protocol["rounds"]) for arm in protocol["learning_arms"]}
    if {p.stem for p in (root / "learning").glob("*.json")} != expected:
        raise ValueError("Learning evidence does not match the complete frozen update grid")
    rows, probes = [], set()
    for key in sorted(expected):
        proposal = module.read(root / "learning" / (key + ".json"))
        identity = {k: proposal[k] for k in ("history", "round", "arm")}
        if key != f"h{identity['history']}-r{identity['round']}-{identity['arm']}":
            raise ValueError("Learning filename identity differs")
        if proposal.get("final_feedback_used") is not False:
            raise ValueError("Final feedback must not enter learning")
        probes.update(proposal["probe_hashes"])
        rows.append({**identity, "valid": proposal["valid"], "changed": proposal["changed"],
                     "operations": len(proposal["operations"]), "probe_refs": len(proposal["probe_hashes"])})
    aggregate = {"proposals": len(rows), "valid": sum(r["valid"] for r in rows),
                 "text_changes": sum(r["changed"] for r in rows),
                 "local_operations": sum(r["operations"] for r in rows),
                 "probe_native_evaluations": len(probes)}
    if aggregate != result["learning"]:
        raise ValueError("Learning aggregate differs from immutable proposals")
    if len(probes) != result["evidence_closure"]["extra_probe_native_evaluations"]:
        raise ValueError("Probe execution closure differs")
    return rows


def _delivery_summary(root, result):
    grid = study_module().read(root / "final_rows.json")
    if (grid["record_hash"] != result["final_grid_hash"]
            or grid["frozen_hash"] != result["frozen_hash"]):
        raise ValueError("Final score grid is not bound to frozen result/Skills")
    groups, unique, coverage = {}, {}, {}
    for row in grid["rows"]:
        stage, reason = row["chosen_stage"], row["rollback_reason"]
        if ((stage == "generation" and reason not in {"revision_api_unknown", "revision_delivery_invalid"})
                or (stage == "revision" and reason is not None)
                or stage not in {"generation", "revision"}):
            raise ValueError("Invalid delivery guard metadata")
        record = (stage, reason, row["score"])
        if unique.setdefault(row["solver_record_hash"], record) != record:
            raise ValueError("Aliased final solver records disagree")
        groups.setdefault(row["policy"], Counter())[reason or "no_rollback"] += 1
        counts = coverage.setdefault(row["policy"], {"positions": 0, "nonempty": 0})
        counts["positions"] += 1
        counts["nonempty"] += row["skill_hash"] != hashlib.sha256(b"").hexdigest()
    expected = result["summary"].get("logical_rows", result["summary"].get("positions"))
    if len(grid["rows"]) != expected:
        raise ValueError("Final position count differs")
    return {"by_policy_positions": {k: dict(v) for k, v in groups.items()},
            "skill_coverage_positions": coverage,
            "unique_trajectories": len(unique),
            "unique_rollbacks": sum(stage == "generation" for stage, _, _ in unique.values())}


def render(protocol, result, audit, proposals, delivery):
    """Only aggregate metadata and frozen scores; no prompt, Skill or answer text."""
    smoke = protocol["design"] == "smoke"
    summary = result["summary"]
    lines = ["# V14 跨域约束反馈与局部 Skill 更新实验", "",
        "本报告仅为 smoke 工程验收，不作有效性或安全性推断。" if smoke else
        "主比较为 Constrained − Independent；全部冻结末轮 Skill 直接进入最终评测，没有选择最优候选或历史。",
        "", "## 方法与对照", "",
        f"模型 {protocol['model']}；{protocol['histories']} 条学习历史 × {protocol['rounds']} 轮 × 两个更新臂。"
        "两臂使用相同 Coding + Spreadsheet 开发任务及 solver/optimizer 调用机会；"
        "Constrained 额外使用预先编写的约束反例测试，并生成与证据关联的局部修改。"
        "这是组合干预：等模型调用机会，但不等 oracle/context 预算，不能分离反例与局部修改的贡献。",
        "三个策略使用相同的生成＋公开反馈修订求解器：仅在修订回复 API/格式不可用时保留可交付初稿；"
        "不根据隐藏分数选择初稿或修订稿。Rule Reasoning 不进入开发反馈，全部 Skill 冻结后才评测。", ""]
    if smoke:
        lines += ["## 工程验收", "", "| 策略 | 全尝试成功率 |", "|---|---:|"]
        for policy, value in summary["success_by_policy"].items():
            lines.append(f"| {LABELS[policy]} | {_pct(value)} |")
        lines += ["", f"共 {summary['positions']} 个策略位置；smoke 不提供主检验、显著性或泛化结论。", ""]
    else:
        counts = summary["structural_clusters_by_domain"]
        base = summary["no_skill_sampling"]
        lines += ["## 冻结后的最终效果", "",
            f"{summary['task_instances']} 个新合成任务，每个结构家族一个实例；"
            + " / ".join(f"{d}: {counts[d]} 家族" for d in DOMAINS) + "。"
            + f"{summary['logical_rows']} 个策略位置对应 {summary['unique_trajectory_receipts']} 条唯一轨迹、"
            + f"{summary['unique_request_hashes']} 次唯一最终请求。",
            f"NoSkill 为 {base['unique_trajectory_receipts']} 条实际轨迹、{base['unique_request_hashes']} 次请求；"
            "每条历史均重新调用，不跨历史复用。实际分开调用不证明提供方随机种子独立；"
            "同一历史内相同任务＋Skill 的别名仅计一次真实成本。",
            "分数为全尝试成功率：交付失败或不可评保留在分母并计 0。"
            "先平均任务内历史，再平均家族内任务、域内家族，最后三域等权。", "",
            "| 策略 | Coding | Spreadsheet | Rule Reasoning | macro | 最差域 | 对 Base 最大域退化 |",
            "|---|---:|---:|---:|---:|---:|---:|"]
        for policy in summary["policies"]:
            row = summary["policy_summary"][policy]
            values = [_pct(row["by_domain"][d]["cluster_equal_all_attempt_success"]) for d in DOMAINS]
            values += [_pct(row["macro_all_attempt_success"]), _pct(row["worst_domain_all_attempt_success"]),
                       f"{100 * row['maximum_domain_drop_vs_no_skill']:.2f} pp"]
            lines.append("| " + LABELS[policy] + " | " + " | ".join(values) + " |")
        lines += ["", "### 交付与可评分层（策略位置计数）", "",
            "| 策略 | 位置 | 交付失败 | 已交付但不可评 | 可评成功率（条件诊断） | 非空 Skill 覆盖 |",
            "|---|---:|---:|---:|---:|---:|"]
        for policy in summary["policies"]:
            row = summary["policy_summary"][policy]
            lines.append(f"| {LABELS[policy]} | {row['positions']} | {row['delivery_invalid']} | "
                f"{row['delivery_valid_oracle_unknown']} | {_pct(row['available_semantic_success_diagnostic'])} | "
                f"{_pct(row['nonempty_skill_coverage'])} |")
        lines += ["", "条件可评成功率不能替代全尝试主分数；非空文字不证明学到新机制或实际遵循 Skill。", "",
            "### 各历史 macro", "", "| 历史 | NoSkill | Independent | Constrained |", "|---|---:|---:|---:|"]
        for h in summary["histories"]:
            lines.append(f"| {h} | " + " | ".join(_pct(summary["policy_summary"][p]["by_history"][str(h)]["macro"])
                         for p in summary["policies"]) + " |")
        lines += ["", "历史间波动混合了 Skill 学习差异与求解采样差异，不能单独解释为模型随机性。", "",
            "### 预设主比较：Constrained − Independent", "",
            "| 终点 | 差值 | 家族 bootstrap 95% CI | 双侧 p | Holm p | sign-flip |",
            "|---|---:|---|---:|---:|---|"]
        main = summary["comparisons"]["constrained_vs_independent"]
        for endpoint in ("macro", "spreadsheet"):
            measure = main["macro"] if endpoint == "macro" else main["by_domain"][endpoint]
            correction = summary["primary_endpoints"][endpoint]
            method = "精确" if measure["sign_flip"]["exact"] else "固定种子 Monte Carlo（+1）"
            lines.append(f"| {endpoint} | {_pp(measure['mean_delta'])} | {_ci(measure)} | "
                f"{correction['p_two_sided']:.4f} | {correction['holm_adjusted_p']:.4f} | {method} |")
        lines += ["", "两个主终点作 Holm 校正；CI 按域内家族分层重采样，条件于已冻结学习历史。"
            "3 条历史和家族内实例不能充当更多独立结构家族。每域 8 家族仍低功效；"
            "若 8 个非零家族差异同向，单域双侧精确 p 最小为 2/2⁸ = 0.0078125，少于 8 个非零差异时更粗。"
            "零宽 bootstrap 区间不证明精确、等效或安全；CI 与 sign-flip 并非同一检验的互逆结果。", "",
            "### 探索性比较（不作为额外确认性发现）", "",
            "| 比较 | 终点 | 差值 | 95% CI | 未校正 p |", "|---|---|---:|---|---:|"]
        for key, comparison in summary["comparisons"].items():
            endpoints = ("coding", "rule_reasoning") if key == "constrained_vs_independent" else ("macro", *DOMAINS)
            for endpoint in endpoints:
                measure = comparison["macro"] if endpoint == "macro" else comparison["by_domain"][endpoint]
                lines.append(f"| {key} | {endpoint} | {_pp(measure['mean_delta'])} | {_ci(measure)} | "
                             f"{measure['p_two_sided']:.4f} |")
        lines += ["", "### 配对 gain/loss 与未知", "",
            "| 比较 | win | loss | tie | 任一不可评 | 可评失败损失 | 交付失败损失 | 已交付不可评损失 |",
            "|---|---:|---:|---:|---:|---:|---:|---:|"]
        for key, comparison in summary["comparisons"].items():
            counts = comparison["counts"]
            values = [str(counts[k]) for k in ("wins", "losses", "ties", "paired_unknown",
                "confirmed_semantic_losses", "delivery_losses", "delivered_oracle_unknown_losses")]
            lines.append("| " + key + " | " + " | ".join(values) + " |")
        lines += ["", "上述为相关位置计数，不是独立试验数；unknown 可与 win/loss 重叠。"
            "可评失败可能包含运行异常，不能把全部 loss 称为纯推理错误或机制毒害。", ""]
    lines += ["## 全部更新与交付保护", "",
        "| 历史 | 轮次 | 更新臂 | 有效 | 改变父 Skill | 局部操作数 | probe 引用数 |",
        "|---|---|---|---:|---:|---:|---:|"]
    for p in proposals:
        lines.append(f"| {p['history']} | {p['round']} | {p['arm']} | {int(p['valid'])} | "
                     f"{int(p['changed'])} | {p['operations']} | {p['probe_refs']} |")
    lines += ["", f"全部 {len(proposals)} 次更新均保留；有效 {result['learning']['valid']} 次，"
        f"文本变化 {result['learning']['text_changes']} 次。"
        f"约束 probe 共 {result['learning']['probe_native_evaluations']} 次唯一额外原生评估；"
        "引用数可能因同一父链别名重复，不能直接作执行成本。没有 selection gate 或挑选最好候选。"
        "有效但未改变文本可为合法保留/弃权，不是解析失败，也不能算作学到新 Skill；"
        "最终空 Skill 与同历史 NoSkill 可精确共享轨迹，其无退化不能证明已学出泛化能力。", "",
        "| 最终策略 | 非空 Skill / 位置 | 修订 API 不可用后保留初稿 | 修订格式不可用后保留初稿 |",
        "|---|---:|---:|---:|"]
    for policy, counts in delivery["by_policy_positions"].items():
        coverage = delivery["skill_coverage_positions"][policy]
        lines.append(f"| {LABELS[policy]} | {coverage['nonempty']}/{coverage['positions']} | "
                     f"{counts.get('revision_api_unknown', 0)} | "
                     f"{counts.get('revision_delivery_invalid', 0)} |")
    lines += ["", f"以上是策略位置；去重后最终 {delivery['unique_trajectories']} 条真实轨迹中，"
        f"{delivery['unique_rollbacks']} 条触发交付保护。该数字不是隐藏语义修复收益；"
        "初稿仍可语义失败，不把保护后的可交付率解释为跨域泛化。", ""]
    ledger, closure = result["ledger"], result["evidence_closure"]
    lines += ["## 实际成本与离线核验", "",
        f"逻辑调用 {ledger['cached_logical_calls']}/{ledger['max_logical_calls']}；"
        f"HTTP 尝试 {ledger['http_attempts_from_cached_records']}；成功 {ledger['successful_calls']}；"
        f"终止错误 {ledger['terminal_errors']}。"
        f"闭合账本包含 solver 请求 {closure['unique_solver_requests']}、optimizer 请求 {closure['unique_optimizer_requests']}。",
        f"记录输入 token {ledger['prompt_tokens']}、输出 token {ledger['completion_tokens']}、"
        f"总 token {ledger['total_tokens']}；{ledger['missing_usage_calls']} 次缺少 usage。"
        "缺失 usage 不视作实际零消耗，不推算未核实价格。",
        f"已锁定回放并核对 {audit['verified_evidence_files']} 个证据文件；报告阶段模型调用 0、原生执行 0，"
        "整个实验目录逐文件字节不变。稳定摘要仅排除根级 supervisor.log 调度日志；"
        "回放前后字节检查仍包含该日志，所有科学回执均纳入摘要。",
        f"结果哈希：{result['record_hash']}；审计哈希：{audit['record_hash']}。", "",
        "## 解释边界与下一步", "",
        "这是新编合成结构上的探索性实验，不是公开 benchmark 复现；两个自写更新器均非原生 SkillOpt，"
        "未运行 DeepResearch，也未识别 Research/Rubric 独立贡献。当前比较同时改变约束证据、上下文与局部更新形式。"
        "与 V12 的任务面板和求解器均不同，不能把跨版本分数差直接归因于某一个改动。",
        "下一步在新且更多独立家族、公开 benchmark 上冻结评测，并以等 oracle/context 预算拆分 probe 与局部更新消融；"
        "增加同族变体或只挑有利历史不能代替独立家族。没有显著退化不等于无害，本实验不提供安全、非劣效或普遍跨域泛化认证。", ""]
    return "\n".join(lines)


def report(output, report_path, *, repo=REPO):
    repo = Path(repo).resolve()
    with completed_replay(repo, output) as audited:
        root, protocol, result = (audited[k] for k in ("root", "protocol", "result"))
        target = report_target(report_path, repo)
        if target.is_relative_to(root) or str(target.relative_to(repo)) in protocol["source_hashes"]:
            raise ValueError("Report cannot overwrite frozen sources or experiment evidence")
        proposals = _learning_rows(root, protocol, result)
        delivery = _delivery_summary(root, result)
        stable = {k: v for k, v in audited["before"].items() if k != "supervisor.log"}
        audit = seal({"version": "v14-report-locked-completed-replay-v1",
            "result_hash": result["record_hash"], "protocol_hash": protocol["record_hash"],
            "verified_evidence_files": len(stable),
            "run_files_hash": hashlib.sha256(json.dumps(stable, sort_keys=True).encode()).hexdigest(),
            "operational_log_exclusions": ["supervisor.log"],
            "replay_byte_equality_includes_operational_logs": True,
            "model_api_calls": 0, "native_executions": 0, "run_files_unchanged": True})
        content = render(protocol, result, audit, proposals, delivery)
        if study_module().source_hashes(repo) != protocol["source_hashes"] or tree(root) != audited["before"]:
            raise ValueError("Frozen sources/evidence changed before report publication")
        existed = target.exists()
        write_immutable_text(target, content)
    return {"report": str(target), "created": not existed, "result_hash": result["record_hash"],
            "report_sha256": hashlib.sha256(content.encode()).hexdigest(), "audit_hash": audit["record_hash"],
            "model_api_calls": 0, "native_executions": 0, "run_files_unchanged": True}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args(argv)
    print(json.dumps(report(args.output, args.report), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
