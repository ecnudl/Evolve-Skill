"""Read-only rendering of already audited V17 results; no new evaluation."""

from pathlib import Path

from skillopt.coevolution_v12.study import read


def render(root):
    root = Path(root)
    result, protocol = read(root / "results.json"), read(root / "protocol.json")
    if not result["complete"] or result["protocol_hash"] != protocol["record_hash"]:
        raise ValueError("Only a completed, bound V17 result can be reported")
    screen = result["screen"]
    lines = ["# V17：任务级跨域反馈实验报告", "",
        f"状态：`{result['status']}`；设计：`{result['design']}`；模型：`{protocol['model']}`。", "",
        "本轮为新合成机制实验，不是公开 benchmark 或原版 SkillOpt 复现；未开启新 Research 干预。", "",
        "## 开发筛查", "",
        f"No-Skill：{screen['passed']}/{screen['tasks']}；语义失败 {screen['semantic_failures']}，"
        f"涉及 {len(screen['failure_families'])} 个结构族；oracle unknown {screen['oracle_unknown']}。", "",
        f"继续条件满足：{screen['scientific_threshold_met']}；smoke 绕过科学门槛：{screen['smoke_bypasses_scientific_screen']}。", ""]
    if result["status"] == "screen_stopped":
        lines += ["本轮按预登记规则停止：未启动 Skill 分叉、独立准入或最终模型求解。",
                  "这说明当前开发题的有效学习信号不足或存在 unknown，不是方法无效的证明。不得追加样本直到出现正结果。", ""]
    else:
        summary = result["summary"]
        lines += ["## 冻结 raw Skill 结果", "",
            "| 条件 | Coding | Spreadsheet | 未见 Rule | 域等权平均 | 语义失败 | 交付失败 |",
            "|---|---:|---:|---:|---:|---:|---:|"]
        for arm, row in summary["arms"].items():
            domains = row["by_domain"]
            scores = [f"{domains[d]['family_weighted_success_rate']:.2%}" for d in ("coding", "spreadsheet", "rule_reasoning")]
            lines.append(f"| {arm} | " + " | ".join(scores) +
                         f" | {row['macro_success_rate']:.2%} | {row['semantic_failures']} | {row['delivery_failures']} |")
        lines += ["", "local 与 cross_raw 比较反馈来源；cross_raw 与 cross_structured 使用完全相同事实，仅比较组织方式。",
                  "所有组共用求解器和一次公开反馈修订；最终无进化验证器在线辅助。", "",
                  "## 配对比较", "",
                  "| 比较 | 宏平均差值（百分点） | 95% 聚类区间 | 最差领域差值（百分点） |",
                  "|---|---:|---|---:|"]
        for name, comparison in summary["comparisons"].items():
            lo, hi = comparison["macro_delta_ci95"]
            lines.append(f"| {name} | {comparison['macro_delta'] * 100:+.2f} | "
                         f"[{lo * 100:+.2f}, {hi * 100:+.2f}] | {comparison['worst_domain_delta'] * 100:+.2f} |")
        lines += ["", "结构族为重采样单位，变体和历史不算新族；区间条件于已观察历史，未作多重比较校正。", "",
                  "## 独立经验准入", "", "| history | 候选 | 决策 | 范围 |", "|---|---|---|---|"]
        for gate in result["gates"]:
            v = gate["verdict"]
            lines.append(f"| {gate['history']} | {gate['arm']} | {v['decision']} | {v['scope']} |")
        lines += ["", "Gate 只批准经验支持的 Coding／Spreadsheet 入口；Rule 不在获批部署范围。零损失不等于安全保证。",
                  "raw Skill 成绩不因 gate 拒绝而删除；Base 回退不算 Skill 自身泛化收益。", ""]
        if result.get("deployment_summary"):
            lines += ["### 同批轨迹的部署诊断", "",
                      "| 策略 | 域等权平均 | 候选使用位置 / 总位置 |", "|---|---:|---:|"]
            for arm, row in result["deployment_summary"]["arms"].items():
                if arm == "no_skill":
                    continue
                cov = result["deployment_coverage"][arm]
                lines.append(f"| {arm} | {row['macro_success_rate']:.2%} | {cov['candidate_positions']}/{cov['positions']} |")
            lines += ["", "这是同批 raw/Base 轨迹的离线策略重放，不是独立在线重复，不使用隐藏机制标签逐题路由。", ""]
    ledger = result["ledger"]
    lines += ["## 成本、结论边界与后续", "",
        f"逻辑调用 {ledger['cached_logical_calls']}；HTTP 尝试 {ledger['http_attempts_from_cached_records']}；"
        f"终止 API 错误 {ledger['terminal_errors']}；总 tokens {ledger['total_tokens']}。", "",
        "判断方法有效需要 raw Skill 在未见结构族／领域上的真实收益和低负迁移，不能只看最高平均数或全部 fallback。",
        "若只有交付改善则报告工程收益；若开发满分则改下一版开发难度而不消费本版 final；若跨域反馈无收益则检查新增事实是否改变了 Skill 程序。",
        "本轮结果不能替代 Skill 冻结后的公开多 benchmark 评测。", "",
        f"结果哈希：`{result['record_hash']}`。", ""]
    return "\n".join(lines)
