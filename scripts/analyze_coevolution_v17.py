"""Read-only, zero-API interpretation of a completed V17 study.

This operational report does not change frozen scientific metrics or select
new candidates. It writes only a separate derived Markdown report in docs.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))


def interpret(result):
    if result.get("complete") is not True or result.get("status") not in {"completed", "screen_stopped"}:
        raise ValueError("Interpret only explicitly completed V17 evidence")
    screen = result["screen"]
    lines = ["# V17 结果分析：Skill 泛化与稳定性", "",
        f"运行状态：`{result['status']}`；设计：`{result['design']}`。", "",
        "本次为新合成任务上的探索性实验，不是公开 benchmark 或统计安全认证。", "",
        "## 做了什么", "",
        "先由 Coding 来源轨迹产生共同父 Skill，再分为本地反馈、跨域普通反馈、跨域结构反馈三臂。"
        "后两臂使用同一组实际轨迹与事实，只比较组织方式。候选冻结后分别评估原始内容和独立准入后的 Base 回退策略。", ""]
    if result["design"] == "smoke":
        lines += ["本文件来自 smoke：仅验证流程，不可作为方法有效性结果。", ""]
    lines += ["## 开发学习空间", "",
        f"No-Skill 在开发筛查中成功 **{screen['passed']}/{screen['tasks']}**；"
        f"可执行语义失败 **{screen['semantic_failures']}**，涉及 **{len(screen['failure_families'])}** 个结构族；"
        f"执行／交付 unknown **{screen['oracle_unknown']}**。", ""]
    if result["status"] == "screen_stopped":
        if screen["oracle_unknown"]:
            conclusion = "筛查包含不可用结果，未满足完整证据要求；不能把这些结果解释为模型语义能力不足。"
        elif screen["semantic_failures"] == 0:
            conclusion = "没有发现可执行语义错误，当前开发题未提供足够的学习空间；继续这批题无法有效检验泛化增益。"
        else:
            conclusion = "语义错误数量或结构族覆盖未达到预登记门槛，学习信号不足，按规则停止。"
        lines += [conclusion, "",
            "**没有运行 Skill 分叉、独立准入或最终模型评测。** 这不是泛化方法的负结果，也不是正结果；不能制造不存在的 final 分数。", "",
            "下一步：根据这次开发诊断另立协议，优先接入有自然错误的公开开发任务；保留该批完整记录，不删除已通过题、不追加到显著。"]
    else:
        summary = result["summary"]
        by_arm = summary["arms"]
        base = by_arm["no_skill"]["macro_success_rate"]
        names = ("parent", "local_feedback", "cross_raw_feedback", "cross_structured_feedback")
        lines += ["## 原始 Skill：是否真的提升泛化？", "",
            "| 条件 | Coding | Spreadsheet | 未见 Rule | 三域平均 | 相对 Base 最差域变化 |",
            "|---|---:|---:|---:|---:|---:|"]
        for name in ("no_skill", *names):
            row = by_arm[name]
            cells = row["by_domain"]
            values = [f"{cells[d]['family_weighted_success_rate']:.2%}" for d in ("coding", "spreadsheet", "rule_reasoning")]
            worst = min(cells[d]["family_weighted_success_rate"]
                        - by_arm["no_skill"]["by_domain"][d]["family_weighted_success_rate"] for d in cells)
            lines.append("| " + name + " | " + " | ".join(values)
                         + f" | {row['macro_success_rate']:.2%} | {worst * 100:+.2f} pp |")
        better = [name for name in names if by_arm[name]["macro_success_rate"] > base + 1e-12]
        lines += ["", ("观察到平均成绩高于 Base 的条件：" + "、".join(better) +
                        "。这只是本次描述性收益，还须结合逐域损失和对照区间。") if better else
                  "**没有原始 Skill 条件在三域平均上超过 No-Skill，尚不能声称获得泛化增益。**", ""]
        if base == 1:
            lines += ["最终 No-Skill 满分，存在天花板：可以观察干扰，不能据此证明 Skill 带来正迁移。", ""]
        lines += ["## 两个核心对照", ""]
        for name, meaning in (("cross_raw_feedback_vs_local_feedback", "跨域证据相对本地证据"),
                              ("cross_structured_feedback_vs_cross_raw_feedback", "同证据结构化组织相对普通组织")):
            comparison = summary["comparisons"][name]
            lo, hi = comparison["macro_delta_ci95"]
            interval = "区间包含零，方向尚不稳定" if lo <= 0 <= hi else "本次探索性区间未包含零，但样本少且未作多重比较校正"
            lines += [f"- {meaning}：平均差值 **{comparison['macro_delta'] * 100:+.2f} pp**，"
                      f"95% 结构族区间 [{lo * 100:+.2f}, {hi * 100:+.2f}]；{interval}。"]
        lines += ["", "这些区间条件于已观察学习历史，同题变体、重复历史和共享调用不算额外独立任务。", "",
                  "## 稳定性与范围准入", ""]
        for name in names:
            row = by_arm[name]
            losses = sum(cell["vs_no_skill"]["losses"] for cell in row["by_domain"].values())
            lines.append(f"- {name}：Base 成功而 Skill 失败的逻辑位置 **{losses}**；"
                         f"语义失败 {row['semantic_failures']}，交付失败 {row['delivery_failures']}，"
                         f"交付未知 {row['delivery_unknown']}，执行未知 {row['execution_unknown']}。")
        coverage = result.get("deployment_coverage", {})
        for name, values in coverage.items():
            lines.append(f"- {name} 实际使用候选 **{values['candidate_positions']}/{values['positions']}** 个位置。")
        if coverage and all(value["candidate_positions"] == 0 for value in coverage.values()):
            lines += ["", "**所有经验准入策略均回退 Base。这不证明 Skill 泛化成功，也不能仅凭部署成绩不降证明 gate 有效。**"]
        lines += ["", "范围准入只使用可信环境 domain，不使用隐藏机制标签逐题选 Skill；Rule 从未获部署批准。"
                  "部署成绩是同批轨迹的策略重放，不是新的独立在线样本。", "",
                  "## 下一步", "",
                  "优先追踪同证据分叉中真实胜负：是否改变了程序性 Skill、是否修复语义错误，以及是否产生新的领域损失。"
                  "有稳定 raw 收益才扩展公开冻结评测与多轮验证器／Research；只有 gate 保护则只报告范围控制贡献。"
                  "这些最终任务现在已经用于分析，后续改算法必须另留新最终集。"]
    ledger = result["ledger"]
    lines += ["", "## 成本与审计", "",
        f"真实逻辑调用 {ledger['cached_logical_calls']}，HTTP 尝试 {ledger['http_attempts_from_cached_records']}，"
        f"终止 API 错误 {ledger['terminal_errors']}，记录总 tokens {ledger['total_tokens']}。", "",
        "本报告仅解析已封存数据并复算统计，不调用模型，不重跑任务，不修改成绩。", "",
        f"结果哈希：`{result['record_hash']}`。", ""]
    return "\n".join(lines)


def main(argv=None):
    from scripts.coevolution_v17 import report_path
    from skillopt.coevolution_v17 import core, study
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args(argv)
    root, target = study.safe_root(REPO, args.output), report_path(REPO, args.report)
    result, protocol = study.read(root / "results.json"), study.read(root / "protocol.json")
    if (result["protocol_hash"] != protocol["record_hash"]
            or study.source_hashes(REPO) != protocol["source_hashes"]):
        raise ValueError("Frozen protocol/source mismatch")
    if result["status"] == "completed":
        final = study.read(root / "final_rows.json")
        if final["record_hash"] != result["final_rows_hash"]:
            raise ValueError("Final result grid differs")
        panel = study.read(root / "private_panel.json")
        summary = core.analyze(final["rows"], expected_tasks=[t["id"] for t in panel["groups"]["final"]],
            expected_arms=list(study.POLICIES), expected_histories=list(range(protocol["histories"])))
        if summary != result["summary"]:
            raise ValueError("Derived statistics disagree with frozen result")
    target.write_text(interpret(result), encoding="utf-8")
    print(str(target))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
