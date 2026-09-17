"""Derived evidence-bound report; never calls models or tunes frozen choices."""

from pathlib import Path

from . import core, study


def render(root):
    root = Path(root)
    result, protocol = study.read(root / "results.json"), study.read(root / "protocol.json")
    rows = study.read(root / "final_rows.json")
    manifest = study.read(root / "data_manifest.json")
    if (result.get("complete") is not True or result["protocol_hash"] != protocol["record_hash"]
            or rows["record_hash"] != result["final_rows_hash"]
            or manifest["record_hash"] != protocol["data_manifest_hash"]):
        raise ValueError("Report requires bound completed evidence")
    expected_tasks = [r["id"] for domain in study.DOMAINS for r in manifest["splits"][domain]["final"]]
    summary = core.analyze(rows["rows"], expected_tasks=expected_tasks,
                           expected_arms=list(study.ARMS), expected_histories=list(study.HISTORIES))
    if summary != result["summary"]:
        raise ValueError("Report recomputation differs from sealed final result")
    lines = ["# V18：公开任务上的 Skill 跨域更新与稳定性", "",
        "状态：已完成并由宿主原生指标评测；模型 glm-5.3。", "",
        "本轮使用公开 SearchQA 与 MBPP-sanitized 的预登记兼容子集，"
        "不是 canonical MBPP 排名、未见领域测试、完整持续协同进化或安全认证。", "",
        "## 方法", "",
        "复用两条真实学习得到的 SearchQA 父 Skill；在新的 SearchQA/Coding 开发题上生成"
        "No-Skill 与父 Skill 的配对执行证据。相同父 Skill、相同事实分别进行一次整段更新与分层更新。"
        "分层更新生成共享过程和 Coding 补丁，SearchQA 局部片段保留原父文本，但新增共享过程仍可能干扰来源任务。", "",
        "所有候选、经验准入和域级映射先冻结，再释放最终题。每题一次生成，无测试反馈修订；"
        "Coding 是受限 Python 原生断言，SearchQA 是原有 EM/F1。没有新增 Research 干预。", "",
        "## 原始 Skill 成绩", "",
        "| 条件 | SearchQA EM | Coding 全断言通过 | 两域等权平均 | 最差域 | unknown |",
        "|---|---:|---:|---:|---:|---:|"]
    for arm in study.ARMS:
        row = summary["arms"][arm]
        lines.append(f"| {arm} | {row['by_domain']['searchqa']['all_attempt_success_rate']:.2%}"
            f" | {row['by_domain']['coding']['all_attempt_success_rate']:.2%}"
            f" | {row['macro_success_rate']:.2%} | {row['worst_domain_success_rate']:.2%} | {row['unknown']} |")
    counts = {d: len(manifest["splits"][d]["final"]) for d in study.DOMAINS}
    lines += ["", f"最终新预留题：SearchQA {counts['searchqa']}、Coding {counts['coding']}；"
              "2 条既有来源历史。重复历史不是新题，问题哈希去重不保证语义独立；unknown 保留在全尝试分母。", "",
              "## 两个核心对照与历史一致性", "",
              "| 对照 | 平均差值 | 95% 问题簇区间 | h1 差值 | h2 差值 |",
              "|---|---:|---|---:|---:|"]
    for name in ("layered_vs_whole", "core_only_vs_parent"):
        item = summary["comparisons"][name]
        lo, hi = item["macro_delta_ci95"]
        lines.append(f"| {name} | {item['macro_delta'] * 100:+.2f} pp | [{lo * 100:+.2f}, {hi * 100:+.2f}]"
            f" | {item['by_history']['1']['macro_delta'] * 100:+.2f} pp"
            f" | {item['by_history']['2']['macro_delta'] * 100:+.2f} pp |")
    lines += ["", "区间条件于两条已观察来源历史；保留题簇内历史相关性，未作多重比较校正。"
              "整段−分层是表示、提示和域级注入方式的联合干预，不是单一机制的因果证明。", "",
              "## 负迁移与准入", "",
              "| 原始候选 | 相对 No-Skill 胜／负 | 相对父 Skill 胜／负 |",
              "|---|---|---|"]
    for arm in study.CANDIDATES:
        base = summary["comparisons"][arm + "_vs_no_skill"]["paired"]
        parent = summary["comparisons"][arm + "_vs_parent"]["paired"]
        lines.append(f"| {arm} | {base['wins']} / {base['losses']} | {parent['wins']} / {parent['losses']} |")
    for name, item in result["deployment_coverage"].items():
        metric = result["deployment_summary"]["arms"][name]["macro_success_rate"]
        lines.append(f"\n- {name}：平均 {metric:.2%}，候选使用 {item['candidate_positions']}/{item['positions']}。")
    lines += ["", "上述部署分数是同批 raw/Base 轨迹按冻结域映射重放，不是新在线抽样。"
              "仅允许独立确认中对 Base 和父 Skill 都有收益且没有观测损失的域；其余回退 Base。"
              "全部回退不能证明 Skill 泛化成功，小样本零损失也不能保证安全。", "",
              "## 结果解释与下一步", ""]
    base = summary["arms"]["no_skill"]["macro_success_rate"]
    layered = summary["arms"]["layered"]["macro_success_rate"]
    generic = summary["arms"]["core_only"]["macro_success_rate"]
    primary = summary["comparisons"]["layered_vs_whole"]
    if layered > base:
        lines.append("分层 Skill 在本批两域平均上高于 No-Skill；这只是描述性收益，仍需检查逐域损失、历史方向与区间。")
    else:
        lines.append("分层 Skill 未在本批两域平均上超过 No-Skill，不能宣称整体泛化收益。")
    if primary["macro_delta"] > 0:
        lines.append("分层相对整段更新的平均差为正；不能仅凭这一点归因于共享机制，需结合 core_only 和逐域保留效果。")
    else:
        lines.append("分层相对整段更新没有观察到正平均增量；不应为了支持结构设计而只挑单域或单历史展示。")
    if generic <= base:
        lines.append("共享部分单独使用未超过 No-Skill 的两域平均；即便分层有效，也不能把其收益自动归功于共享核心。")
    lines += ["",
        "有稳定内容收益：在新的公开任务/历史上扩大验证，再增加 Research/Rubric 演化对照。"
        "仅局部补丁有效：按领域适配与干扰控制报告，不包装成未见域泛化。"
        "只有回退有效：只支持部署保护。若效果不稳定，应先归因实际代码/答案错误及源域遗忘，不重复调同一 final。", "",
        "本批 final 已用于本次报告；任何后续算法更新都需新保留集。", "",
        "## 成本与审计", ""]
    ledger = result["ledger"]
    lines += [f"逻辑调用 {ledger['cached_logical_calls']}；HTTP 尝试 {ledger['http_attempts_from_cached_records']}；"
              f"终止 API 错误 {ledger['terminal_errors']}；total tokens {ledger['total_tokens']}。",
              f"\nSkill 更新有效 {result['learning']['valid']}/{result['learning']['positions']}；"
              "无效更新保留父文本，不重新抽样。",
              f"\n结果哈希：`{result['record_hash']}`。", ""]
    return "\n".join(lines)
