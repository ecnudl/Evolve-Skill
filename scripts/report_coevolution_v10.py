"""Publish aggregate Chinese Coding-transfer results after completed offline audit.

No active study resumption, model API construction, task text, reference code
or hidden assertion disclosure is permitted. Existing different reports are
preserved; publication is immutable and outside frozen experiment inputs.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from scripts import coevolution_v10 as runner  # noqa: E402
from skillopt.coevolution_v5 import core  # noqa: E402
from skillopt.scope_evolution_v2.source_data import write_immutable_text  # noqa: E402


def _pct(value):
    return "不可评" if value is None else f"{100 * value:.2f}%"


def _pp(value):
    return "不可评" if value is None else f"{100 * value:+.2f}pp"


def _p(value):
    return "未计算" if value is None else f"{value:.4g}"


def render(protocol, result, audit):
    """Report only aggregates; never render full source/gate/private task rows."""
    summary, gate, ledger = result["summary"], result["gate"], result["ledger"]
    counts = protocol["counts"]
    smoke = result["smoke_not_effect_evidence"]
    decisions = sorted(gate["decisions"].items(), key=lambda item: int(item[0]))
    labels = {"no_skill": "No-Skill", "initial": "初始占位 Skill（辅助）",
              "raw_transfer": "冻结来源 Skill 直接迁移", "scope_gated": "跨域门控 / 回退"}
    lines = ["# V10 冻结 SearchQA Skill → Coding 迁移报告", "",
        "**Smoke 接口验收，不构成效果证据。**" if smoke else
        "本实验新增 Coding 目标侧的独立迁移检查，不是完整 MBPP 复现，也没有在 Coding 上继续训练 Skill。", "",
        f"模型 `{protocol['model']}`；固定 {len(protocol['histories'])} 个来源学习历史，共享一次 "
        f"{counts['confirmation']} 题 target-confirmation；最终独立审计 {counts['final']} 题。",
        "使用 MBPP-sanitized 的预登记静态兼容子集：确认池来自原 train/validation，审计池来自原 test。"
        "每个任务/不同 Skill 文本只生成一次代码；相同文本精确复用请求；不向模型提供测试示例、参考解或测试反馈。", "",
        "## 验证门做了什么", "",
        "| 来源历史 | 真实学到新 Skill | 允许目标使用 | 对 Base 胜/负/平 | 全尝试差值 | 单侧 Holm p | 观测损失比例 |",
        "| --- | --- | --- | --- | --- | --- | --- |"]
    for history, row in decisions:
        lines.append(f"| {history} | {'是' if row['learned'] else '否'} | {'是' if row['approve'] else '否'} | "
            f"{row['wins']}/{row['losses']}/{row['ties']} | {_pp(row['all_attempt_delta'])} | "
            f"{_p(row['holm_one_sided_p'])} | {_pct(row['observed_loss_rate'])} |")
    lines.extend(["", f"同一确认面板仅使用一次；对 {len(gate['family'])} 个不同的真实学习 Skill 进行同族 Holm 控制。"
        f"门槛：至少 {gate['minimum_clusters']} 个独立问题、有正向观测收益、"
        f"Holm 单侧 p≤{gate['alpha']:.2f}、观测损失比例≤{100 * gate['maximum_observed_loss_rate']:.0f}%，"
        "且候选 unknown 不多于 Base。拒绝则使用空 No-Skill，不是保留初始占位 Skill。",
        "这是预登记兼容题群上的探索性范围选择，不是非劣或安全认证；少量观测损失不等于获得风险上界。", ""])
    for history, row in decisions:
        if row["reasons"]:
            lines.append(f"- 历史 {history} 未扩大范围：" + "；".join(row["reasons"]) + "。")
    lines.extend(["", "## 冻结部署后的最终成绩", "",
        "| 政策 | 全尝试任务成功率 | 全尝试断言通过比例 | 可评 / 政策×历史位置 | 唯一实际请求 | 真正新 Skill 使用位置 |",
        "| --- | --- | --- | --- | --- | --- |"])
    for policy, label in labels.items():
        row = summary["policy_summary"][policy]
        lines.append(f"| {label} | {_pct(row['all_attempt_task_success'])} | "
            f"{_pct(row['all_attempt_assertion_fraction'])} | {row['oracle_available']}/{row['n_positions']} | "
            f"{row['unique_requests']} | {summary['actual_learned_usage'][policy]} |")
    lines.extend(["", f"共有 {summary['n_questions']} 个题目、{summary['n_question_clusters']} 个问题簇、"
        f"{summary['n_observation_positions']} 个政策×历史位置，实际 {summary['unique_actual_requests']} 条最终生成请求。"
        f"跨域门控中 {summary['scope_fallback_positions']} 个位置回退 No-Skill。",
        "位置、测试断言、参数或共享请求均不能当作新的独立题目；单函数题不是仓库级工程家族。"
        "全尝试分母保留全部不可评/失败位置；unknown 仅在该汇总中记为未成功，不当作已确认语义错误。", "",
        "逐来源历史的最终任务成功率（No-Skill / 初始 / 直接迁移 / 门控）：", ""])
    for history in summary["histories"]:
        rates = [_pct(summary["policy_summary"][policy]["per_history"][str(history)]["all_attempt_task_success"])
                 for policy in labels]
        lines.append(f"- 历史 {history}：" + " / ".join(rates) + "。")
    lines.extend(["", "## 配对比较", "",
        "| 比较 | 问题簇平均差 | 簇 bootstrap 95% CI | 双侧 sign-flip p | 主比较 Holm p | 胜/负/平 |",
        "| --- | --- | --- | --- | --- | --- |"])
    for key, label in (("scope_gated_vs_raw_transfer", "门控 − 直接迁移"),
                       ("scope_gated_vs_no_skill", "门控 − No-Skill"),
                       ("raw_transfer_vs_no_skill", "直接迁移 − No-Skill（辅助）"),
                       ("scope_gated_vs_initial", "门控 − 初始（辅助）")):
        comparison = summary["comparisons"][key]
        metric = comparison["metrics"]["task_success"]
        inference, tally = metric["cluster_inference"], metric["all_attempt"]
        interval = inference["ci95"]
        lines.append(f"| {label} | {_pp(inference['mean_delta'])} | "
            f"[{_pp(interval['low'])}, {_pp(interval['high'])}] | {_p(inference['sign_flip']['p_two_sided'])} | "
            f"{_p(comparison.get('primary_holm_adjusted_p'))} | {tally['wins']}/{tally['losses']}/{tally['ties']} |")
    lines.extend(["", "先在问题簇内平均来源历史，再做区间与检验；统计条件于这些已冻结的学习历史，"
        "不等于充分覆盖所有学习随机性。不能仅因 bootstrap 区间排除零而忽略主检验或多重比较。", ""])
    for policy, label in (("raw_transfer", "直接迁移"), ("scope_gated", "门控")):
        comparison = summary["comparisons"][policy + "_vs_no_skill"]
        loss = comparison["right_correct_left_unsuccessful"]
        lines.append(f"- {label}：Base 正确而该臂未成功 {loss['count']}/{loss['all_positions_denominator']} 个位置；"
            f"已评分损失 {loss['confirmed_scored_losses']}，unknown 损失 {loss['unknown_left_losses']}。")
    fallback = summary["scope_fallback_positions"]
    positions = summary["policy_summary"]["scope_gated"]["n_positions"]
    if fallback == positions:
        lines.extend(["", "本次门控全部回退 No-Skill。因此门控与 Base 相同是精确请求别名的设计结果，"
                      "不是学到跨域能力，也不能把两臂相同当作独立重复验证。"])
    main = summary["comparisons"]["scope_gated_vs_raw_transfer"]
    jointly = main["metrics"]["task_success"]["jointly_available_diagnostic"]
    if (jointly["n"] and jointly["wins"] == jointly["losses"] == 0
            and main["jointly_available_positions"] < main["n_question_history_positions"]):
        lines.extend(["", "门控与直接迁移在双方可评的子集没有任务成功率胜负；其全尝试差值只涉及不可评位置，"
                      "不能据此宣称语义正迁移或负迁移，也不能删除 unknown 后重算主结果。"])
    lines.extend(["", "## 参考解、不可评与成本", ""])
    for split, label in (("confirmation", "确认"), ("final", "最终审计")):
        reference = result["reference_summary"][split]
        lines.append(f"- {label}参考校准：{reference['valid']}/{reference['total']} 可用，{reference['unknown']} unknown；"
                     "参考失败不补抽、不换题，各政策保持预算且该题不可评。")
    lines.append("- 全运行唯一解题请求的结果类别：" + "；".join(
        f"`{key}`={count}" for key, count in sorted(result["outcome_categories"].items())) + "。")
    lines.extend(["", f"逻辑调用 {ledger['cached_logical_calls']} / 上限 {ledger['max_logical_calls']}；"
        f"HTTP attempts {ledger['http_attempts_from_cached_records']}；API 成功 {ledger['successful_calls']}，"
        f"终止失败 {ledger['terminal_errors']}。接口报告 prompt {ledger['prompt_tokens']:,}、"
        f"completion {ledger['completion_tokens']:,}、total {ledger['total_tokens']:,} tokens；"
        f"{ledger['missing_usage_calls']} 次缺失 usage。这不是账单；中间失败未回报消耗未知。",
        "这些是本次目标域调用，不重复计入历史 SearchQA 学习成本。各臂相同生成上限不意味着相同实际 tokens。", "",
        "## 能说明与不能说明什么", "",
        "本轮将真实学习得到的来源 Skill 冻结后带到另一领域，检查直接迁移、范围选择和回退的差别。"
        "没有重新进化 Skill，没有启用新的 Research Rubric，也不评价完整的 Skill/验证器协同进化。",
        "兼容筛选、无测试示例、受限 Python 和每 case 全新环境都与原生 MBPP 评测不同；"
        "公开老题的模型训练污染与成绩饱和仍未知，不得声称 canonical MBPP 排名或普适跨域安全。",
        "旧 SearchQA final 已在上一轮报告；不能与本次 Coding 审计拼成一次全新的共同盲测。"
        "目标仍是多个领域总体较强且少退化，而非每个 benchmark 都达到 SOTA。",
        "下一步应在新的、机制对应的学习源与目标数据上检验正迁移，并保留 near-miss/无关任务的损失检查。"
        "本次确认/审计题不回流候选、Rubric、阈值或数据兼容规则。", "",
        f"完成版离线重算通过：{audit['verified_run_files']} 个运行文件内容 hash 不变，新增模型调用 0。"
        "这是文件内容完整性检查，不声称锁文件 mtime 未变。",
        f"结果 hash：`{result['record_hash']}`。", f"离线审计 hash：`{audit['record_hash']}`。", ""])
    return "\n".join(lines)


def _target(report, root, repo, protocol):
    target = Path(report).absolute() if report is not None else repo / "docs" / f"coevolution-v10-{root.name}-report.md"
    if any(part.is_symlink() for part in (target, *target.parents)):
        raise ValueError("Report paths may not contain symlinks")
    target = target.resolve()
    if target.suffix.lower() != ".md":
        raise ValueError("Report must be a Markdown .md artifact")
    if target.is_relative_to(repo) and not target.is_relative_to(repo / "docs"):
        raise ValueError("Repository reports must remain under docs")
    protected = {(repo / name).resolve() for name in protocol["source_hashes"]}
    if target in protected or target == root or target.is_relative_to(root):
        raise ValueError("Report destination cannot overwrite frozen source or run inputs")
    if target.exists() and not target.is_file():
        raise ValueError("Report destination must be a file")
    return target


def _verify_sources(repo, protocol):
    sources = protocol.get("source_hashes")
    if not isinstance(sources, dict) or not sources:
        raise ValueError("A nonempty frozen source map is required")
    for relative, expected in sources.items():
        path = (repo / relative).resolve()
        if (not path.is_relative_to(repo) or not path.is_file()
                or hashlib.sha256(path.read_bytes()).hexdigest() != expected):
            raise ValueError("Frozen source changed before report publication")


def report(output, report_path=None, repo=REPO):
    repo = Path(repo).resolve()
    root = runner.safe_root(output, repo)
    before = runner.tree_hashes(root)
    replay = runner.completed_replay(root, repo)
    protocol, result, audit = (core.verify(replay[key]) for key in ("protocol", "result", "audit"))
    if (audit.get("complete_integrity_audit") is not True or audit.get("run_files_unchanged") is not True
            or audit.get("model_api_calls") != 0 or result.get("complete") is not True
            or result.get("protocol_hash") != protocol["record_hash"]
            or audit.get("result_hash") != result["record_hash"]
            or runner._read(root / "results.json") != result or runner._read(root / "protocol.json") != protocol):
        raise ValueError("Completed audited result/protocol changed before report generation")
    target = _target(report_path, root, repo, protocol)
    text = render(protocol, result, audit)
    _verify_sources(repo, protocol)
    if runner.tree_hashes(root) != before:
        raise ValueError("Run changed before report publication")
    existed = target.exists()
    if existed and target.read_text(encoding="utf-8") != text:
        raise ValueError("Existing report differs; choose a new --report path")
    write_immutable_text(target, text)
    return {"report": str(target), "report_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "created": not existed, "result_hash": result["record_hash"], "audit_hash": audit["record_hash"],
            "model_api_calls": 0, "run_files_unchanged": True}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, default=None)
    args = parser.parse_args(argv)
    print(json.dumps(report(args.output, args.report), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
