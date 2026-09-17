"""Publish a concise Chinese V9 report only after completed offline verification.

No API client, .env access, experiment resumption, or source/run modifications
are permitted. The report is a new Markdown artifact (or an identical existing
artifact), never an overwrite of experiment inputs or frozen source files.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from scripts import audit_coevolution_v9 as auditor  # noqa: E402
from skillopt.coevolution_v5.core import verify  # noqa: E402


def _read(path):
    return verify(json.loads(path.read_text(encoding="utf-8")))


def _percentage(value):
    return "不可评" if value is None else f"{100 * value:.2f}%"


def _pp(value):
    return "不可评" if value is None else f"{100 * value:+.2f}pp"


def _probability(value):
    return "未计算" if value is None else f"{value:.4g}"


def _yes(value):
    return "是" if value else "否"


def render(protocol, result, audit_result):
    """Render aggregate outcomes only, not task answers or Skill text."""
    design, summary, ledger = protocol["design"], result["summary"], result["ledger"]
    smoke = result["smoke_not_effect_evidence"]
    lines = ["# V9 SearchQA 来源 Skill 学习实验报告", "",
             "**Smoke 接口验收，不构成效果证据。**" if smoke else "本报告为来源领域的单轮 Skill 学习与门控对照，不是跨领域泛化实验。", "",
             f"模型 `{protocol['model']}`；H={design['histories']} 个学习历史，每历史 T={design['train']} 题训练、"
             f"C={design['confirmation']} 题独立确认；F={design['final']} 个最终问题。每历史仅一轮更新。",
             "复用真实 SkillOpt 反思、合并、排序与补丁流程，每历史生成一个候选，由普通门和 Our 门共同选择；"
             "普通臂是预算受控适配，不是论文默认配置的完整复现。", "",
             "## 学到了什么、两道门如何选择", "",
             "| 历史 | 候选文本变化 | 普通门接受 | Our 接受 | 对父版本胜/负 | 单侧 p | Base 正确而候选未成功（含 unknown）/分母 | unknown 父/候选/Base |",
             "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    for history in sorted(result["histories"], key=lambda row: row["history"]):
        gate = history["gate"]
        losses = gate["base_correct_candidate_unsuccessful"]
        unknown = "/".join(str(gate["rates"][key]["unknown"]) for key in ("parent", "candidate", "base"))
        wins = gate["candidate_vs_parent"]
        lines.append(f"| {history['history']} | {_yes(history['candidate_changed'])} | {_yes(gate['standard_accept'])} | "
                     f"{_yes(gate['ours_accept'])} | {wins['wins']}/{wins['losses']} | "
                     f"{_probability(gate['exact_discordant_one_sided_p'])} | "
                     f"{losses['count']}/{losses['base_correct_denominator']} | {unknown} |")
    lines.extend(["", "普通门要求候选原生 EM 严格高于父版本；Our 还要求候选 EM 不低于 No-Skill、"
                  "配对单侧 p≤0.10，且至少 64 个独立确认问题。拒绝保留初始父 Skill，不是回退 No-Skill。"
                  "这些是探索性选择条件，不是安全或非劣认证。确认结果不回传优化器。", "",
                  "## Skill 冻结后的最终成绩", "",
                  "| 政策 | 全尝试 EM | 全尝试 F1 | 可评/位置数 | 唯一实际请求数 | 使用新 Skill 的位置数 |",
                  "| --- | --- | --- | --- | --- | --- |"])
    labels = {"no_skill": "No-Skill", "initial": "初始 Skill（辅助）", "skillopt": "普通 SkillOpt", "ours": "Our"}
    for policy, label in labels.items():
        row = summary["policy_summary"][policy]
        evolved = row.get("evolved_skill_positions")
        lines.append(f"| {label} | {_percentage(row['all_attempt_em'])} | {_percentage(row['all_attempt_f1'])} | "
                     f"{row['oracle_available']}/{row['n_positions']} | {row['unique_requests']} | "
                     f"{evolved if evolved is not None else '—'} |")
    lines.extend(["", f"共有 {summary['n_questions']} 个问题、{summary['n_question_clusters']} 个问题簇，"
                  f"{summary['n_observation_positions']} 个政策×历史位置，实际仅 {summary['unique_actual_requests']} 条解题请求；"
                  f"{summary['aliased_positions_beyond_first_request']} 个位置复用已有请求，不能作为独立样本。",
                  "全尝试分母保留所有失败，缺失记 0 仅用于成功率汇总；unknown 不解释为已确认语义失败。", "",
                  "逐历史最终 EM（No-Skill / 初始 / 普通 / Our）：", ""])
    for history in summary["histories"]:
        scores = [_percentage(summary["policy_summary"][policy]["per_history"][str(history)]["all_attempt_em"])
                  for policy in labels]
        lines.append(f"- 历史 {history}：" + " / ".join(scores) + "。")
    lines.extend(["", "## 主要配对比较", "",
                  "| 比较 | 问题簇均值差 | 簇 bootstrap 95% CI | 双侧 sign-flip p | 主 EM Holm p | 胜/负/平 |",
                  "| --- | --- | --- | --- | --- | --- |"])
    for name, label in (("ours_vs_skillopt", "Our − 普通"), ("ours_vs_no_skill", "Our − No-Skill"),
                        ("skillopt_vs_no_skill", "普通 − No-Skill（辅助）"),
                        ("ours_vs_initial", "Our − 初始（辅助）"),
                        ("skillopt_vs_initial", "普通 − 初始（辅助）")):
        comparison = summary["comparisons"][name]
        metric = comparison["metrics"]["em"]
        inference, tally = metric["cluster_inference"], metric["all_attempt"]
        interval = inference["ci95"]
        lines.append(f"| {label} | {_pp(inference['mean_delta'])} | "
                     f"[{_pp(interval['low'])}, {_pp(interval['high'])}] | "
                     f"{_probability(inference['sign_flip']['p_two_sided'])} | "
                     f"{_probability(comparison.get('primary_em_holm_adjusted_p'))} | "
                     f"{tally['wins']}/{tally['losses']}/{tally['ties']} |")
    lines.extend(["", "先在问题簇内平均学习历史，再计算区间；区间以已观察到的学习历史为条件，"
                  "不能把重复或共享请求当独立 N，也不充分覆盖学习随机性。"
                  "两项主 EM 比较使用 Holm；不能只挑 bootstrap 排除零就宣称显著。", ""])
    for policy, label in (("ours", "Our"), ("skillopt", "普通")):
        loss = summary["comparisons"][policy + "_vs_no_skill"]["right_correct_left_unsuccessful"]
        conditional = _percentage(loss["right_correct_rate"])
        lines.append(f"- {label} 相对 No-Skill 的配对损失：{loss['count']}/{loss['all_positions_denominator']} 个位置；"
                     f"在 Base 正确子集为 {loss['count']}/{loss['right_correct_denominator']}（{conditional}），"
                     f"其中已评分损失 {loss['confirmed_scored_losses']}，unknown {loss['unknown_left_losses']}。")
        if loss["count"] and loss["confirmed_scored_losses"] == 0:
            lines.append(f"  {label} 的这些观测损失全部来自 unknown，而非已评分的错误回答，不能称为 Skill 语义负迁移。")
    main = summary["comparisons"]["ours_vs_skillopt"]
    available = main["metrics"]["em"]["jointly_available_diagnostic"]
    if (available["n"] and available["wins"] == available["losses"] == 0
            and main["jointly_available_positions"] < main["n_question_history_positions"]):
        lines.extend(["", "Our 与普通臂在双方可评子集上没有 EM 胜负；主比较中的分数差异来自至少一方不可评的位置。"
                      "这是可用性诊断，不是 Skill 语义收益或负迁移证据；不能据此删除失败后重算主结果。"])
    changed = sum(history["candidate_changed"] for history in result["histories"])
    standard_accepted = sum(history["gate"]["standard_accept"] for history in result["histories"])
    ours_accepted = sum(history["gate"]["ours_accept"] for history in result["histories"])
    lines.extend(["", "## 当前结论与限制", "",
                  f"本次 {changed}/{design['histories']} 个历史产生文本变化；普通门接受 {standard_accepted} 次，Our 接受 {ours_accepted} 次。",
                  "本实验只隔离门控选择：两臂共用候选，不验证两个优化器协同学习，也没有启用新的 Research Rubric。"
                  "初始 Skill 非空，但实际仅包含标题与“尚无已学规则”的占位文本，不是成熟经验库；"
                  "保留初始版本或其成绩较好，不能称为新 Skill 进化收益。",
                  "最终只评实际选中的部署版本，没有单列所有被拒候选的反事实最终执行，"
                  "因此不能断言某次拒绝避免了实际损害。最终结果不用于重写本次候选、门槛或补抽。",
                  "只有 SearchQA 一个领域、每历史一轮，不能据此声称跨领域正迁移、低毒害性或公开多域 SOTA。", "",
                  "下一步：先根据完整最终差值区分初始 Skill、真实更新及门控选择的贡献；"
                  "随后另行冻结新 Coding / Spreadsheet 数据与跨域确认，推进独立多域学习实验，不复用本次 final 做优化。", "",
                  "## 成本与验收", "",
                  f"逻辑调用 {ledger['cached_logical_calls']}（预设上限 {ledger['max_logical_calls']}），"
                  f"HTTP attempts {ledger['http_attempts_from_cached_records']}，API 成功 {ledger['successful_calls']}，"
                  f"终止失败 {ledger['terminal_errors']}。接口报告 prompt {ledger['prompt_tokens']:,}、"
                  f"completion {ledger['completion_tokens']:,}、total {ledger['total_tokens']:,} tokens；"
                  f"{ledger['missing_usage_calls']} 次无 usage。这不是账单，未返回的中间失败消耗未知。",
                  "共享训练和候选成本只计一次；相同调用额度不等于相同实际 tokens。No-Skill 不承担训练成本。",
                  f"完成版离线重算已通过，{audit_result['verified_run_files']} 个运行文件字节不变，审计新增模型调用为 0。",
                  f"结果 hash：`{result['record_hash']}`。", f"审计 hash：`{audit_result['record_hash']}`。", ""])
    return "\n".join(lines)


def _target(report, root, repo, protocol):
    target = Path(report).absolute() if report is not None else repo / "docs" / f"coevolution-v9-{root.name}-report.md"
    if any(part.is_symlink() for part in (target, *target.parents)):
        raise ValueError("Report paths may not contain symlinks")
    target = target.resolve()
    if target.suffix.lower() != ".md":
        raise ValueError("The report must be a Markdown .md artifact")
    if target.is_relative_to(repo) and not target.is_relative_to(repo / "docs"):
        raise ValueError("Within the repository, reports must stay under docs, never source/data/run directories")
    protected = {(repo / relative).resolve() for relative in protocol["source_hashes"]}
    if target in protected or target == root or target.is_relative_to(root):
        raise ValueError("Cannot use a frozen source or experiment input as the report destination")
    if target.exists() and not target.is_file():
        raise ValueError("Report destination must be a file")
    return target


def _verify_source_hashes(repo, protocol):
    for relative, expected in protocol["source_hashes"].items():
        path = (repo / relative).resolve()
        if (not path.is_relative_to(repo) or not path.is_file()
                or hashlib.sha256(path.read_bytes()).hexdigest() != expected):
            raise ValueError("Frozen source changed before report publication")


def _publish(target, content):
    encoded = content.encode("utf-8")
    if target.exists():
        if target.read_bytes() != encoded:
            raise ValueError("Existing report differs; choose a new --report path")
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=target.parent, prefix=".v9-report-", suffix=".tmp", delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, target)
        except FileExistsError:
            if target.read_bytes() != encoded:
                raise ValueError("Concurrent report differs; existing file is preserved") from None
            return False
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return True


def report(output, report_path=None, repo=REPO):
    """Require completed audit, recheck input hashes, then immutably publish."""
    repo = Path(repo).resolve()
    root = auditor._safe_root(output, repo)
    before = auditor._tree_hashes(root)
    audit_result = auditor.audit(root, repo, require_complete=True)
    if (audit_result.get("complete_integrity_audit") is not True or audit_result.get("run_files_unchanged") is not True
            or audit_result.get("model_api_calls") != 0):
        raise ValueError("Completed read-only verification must succeed before report generation")
    verify(audit_result)
    protocol, result = _read(root / "protocol.json"), _read(root / "results.json")
    if (result.get("complete") is not True or result.get("protocol_hash") != protocol["record_hash"]
            or audit_result.get("result_hash") != result["record_hash"]
            or audit_result.get("summary") != result["summary"] or audit_result.get("ledger") != result["ledger"]):
        raise ValueError("Audited completion changed before report generation")
    target = _target(report_path, root, repo, protocol)
    text = render(protocol, result, audit_result)
    _verify_source_hashes(repo, protocol)
    if auditor._tree_hashes(root) != before:
        raise ValueError("Run inputs changed before report publication")
    created = _publish(target, text)
    return {"report": str(target), "report_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "created": created, "result_hash": result["record_hash"], "audit_hash": audit_result["record_hash"],
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
