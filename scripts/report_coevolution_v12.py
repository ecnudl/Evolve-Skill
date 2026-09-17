"""Publish a Chinese V12 report only after read-only, offline completed replay."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import sys
from contextlib import ExitStack, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from skillopt.coevolution_v5.core import seal  # noqa: E402
from skillopt.coevolution_v12 import runtime, study  # noqa: E402
from skillopt.scope_evolution_v2.source_data import write_immutable_text  # noqa: E402

LABELS = {
    "no_skill": "NoSkill",
    "independent": "Independent（raw）",
    "contrastive": "Contrastive（raw）",
    "selected_independent": "Independent（selected 诊断）",
    "selected_contrastive": "Contrastive（selected 诊断）",
}
DOMAINS = ("coding", "spreadsheet", "rule_reasoning")


def _pct(value):
    return "不可评" if value is None else f"{100 * value:.2f}%"


def _pp(value):
    return f"{100 * value:+.2f} pp"


def _tree(root):
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob("*") if p.is_file()}


def _forbidden(*args, **kwargs):
    raise ValueError("Completed report audit attempted model access or native execution")


def _target(path, repo, root, protocol):
    path = Path(path).absolute()
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError("Symlink report paths are forbidden")
    path = path.resolve()
    if path.suffix != ".md" or not path.is_relative_to(repo / "docs"):
        raise ValueError("Report must be a Markdown file beneath repository docs")
    if path.is_relative_to(root) or str(path.relative_to(repo)) in protocol["source_hashes"]:
        raise ValueError("Report must not overwrite frozen sources or experiment evidence")
    return path


def _learning_rows(root, protocol, result):
    expected = {f"h{h}-r{r}-{a}" for h in range(protocol["histories"])
                for r in range(protocol["rounds"]) for a in protocol["learning_arms"]}
    rows = []
    for directory in ("learning", "selection"):
        if {p.stem for p in (root / directory).glob("*.json")} != expected:
            raise ValueError("Learning/selection report evidence is incomplete or orphaned")
    for key in sorted(expected):
        proposal = study.read(root / "learning" / (key + ".json"))
        selected = study.read(root / "selection" / (key + ".json"))
        identity = {k: proposal[k] for k in ("history", "round", "arm")}
        if any(selected[k] != v for k, v in identity.items()):
            raise ValueError("Learning/selection identity mismatch")
        if key != f"h{identity['history']}-r{identity['round']}-{identity['arm']}":
            raise ValueError("Learning filename identity mismatch")
        rows.append({**identity, "valid": proposal["valid"], "changed": proposal["changed"],
                     "reason": proposal["reason"], "accepted": selected["accept"]})
    aggregate = {"proposals": len(rows), "valid": sum(r["valid"] for r in rows),
                 "text_changes": sum(r["changed"] for r in rows),
                 "selection_acceptances": sum(r["accepted"] for r in rows)}
    if aggregate != result["learning"]:
        raise ValueError("Learning summary disagrees with its immutable records")
    return rows


def render(protocol, result, audit, proposals):
    """Render metadata/scores only, never task bodies, Skill text or answers."""
    smoke = protocol["design"] == "smoke"
    summary = result["summary"]
    lines = ["# V12 跨域 Skill 内容进化实验报告", "",
        "本报告为 smoke 工程验收，不作效果推断。" if smoke else
        "主比较为未经过选择筛选的 Contrastive − Independent；selected 仅为部署诊断。", "",
        "## 做了什么", "",
        f"模型 {protocol['model']}；{protocol['histories']} 条历史 × {protocol['rounds']} 轮 × 两种更新方法。"
        "两臂使用相同 Coding + Spreadsheet 开发任务、更新机会及调用上限；首轮后 Skill 和实际轨迹可以不同，"
        "因此不是完全相同的行为证据。每条求解轨迹均为生成后一次公开反馈修订。",
        "Independent 使用独立记录的固定反馈；Contrastive 增加 NoSkill/current 配对反例及对照指令，"
        "直接修改 Skill 内容。Rule Reasoning 不进入开发和选择反馈。", ""]
    if smoke:
        lines += ["## 接口验收结果", "", "| 策略 | 全尝试成功率 |", "|---|---:|"]
        for policy, value in summary["success_by_policy"].items():
            lines.append(f"| {LABELS[policy]} | {_pct(value)} |")
        lines += ["", f"共 {summary['positions']} 个策略位置；共享轨迹不视作独立重复。"
                  "小样本及 smoke 任务不能用于支持泛化或安全结论。", ""]
    else:
        counts = summary["structural_clusters_by_domain"]
        lines += ["## 冻结后的最终结果", "",
            f"{summary['task_instances']} 个任务变体，结构簇分别为 "
            + " / ".join(f"{d}: {counts[d]}" for d in DOMAINS)
            + f"；{summary['logical_rows']} 个策略位置，对应 {summary['unique_trajectory_receipts']} 条唯一最终轨迹"
            + f"、{summary['unique_request_hashes']} 次唯一最终请求。", "",
            "以下均为全尝试成功率：不可交付/不可评尝试计 0，不从分母删除。先在任务内平均历史，"
            "再平均簇内任务、域内结构簇，最后三个域等权。", "",
            "| 策略 | Coding | Spreadsheet | Rule Reasoning | 域等权 macro | 非空 Skill 覆盖 | 可评位置 |",
            "|---|---:|---:|---:|---:|---:|---:|"]
        for policy in summary["policies"]:
            row = summary["policy_summary"][policy]
            values = [_pct(row["by_domain"][d]["cluster_equal_all_attempt_success"]) for d in DOMAINS]
            values += [_pct(row["macro_all_attempt_success"]), _pct(row["nonempty_skill_coverage"]),
                       f"{row['oracle_available']}/{row['positions']}"]
            lines.append("| " + LABELS[policy] + " | " + " | ".join(values) + " |")
        lines += ["", "非空覆盖仅表示部署了文字，不证明学到了新机制。", "",
            "### 各历史的域等权 macro", "",
            "| 历史 | " + " | ".join(LABELS[p] for p in summary["policies"]) + " |",
            "|---|" + "---:|" * len(summary["policies"])]
        for history in summary["histories"]:
            values = [_pct(summary["policy_summary"][p]["by_history"][str(history)]["macro"])
                      for p in summary["policies"]]
            lines.append(f"| {history} | " + " | ".join(values) + " |")
        main = summary["comparisons"]["contrastive_vs_independent"]
        lines += ["", "### 预设主比较：raw Contrastive − raw Independent", "",
            "| 终点 | 差值 | 结构簇 bootstrap 95% CI | 双侧 p | Holm 校正 p |",
            "|---|---:|---|---:|---:|"]
        for endpoint in ("macro", "rule_reasoning"):
            measure = main["macro"] if endpoint == "macro" else main["by_domain"][endpoint]
            correction = summary["primary_endpoints"][endpoint]
            lines.append(f"| {endpoint} | {_pp(measure['mean_delta'])} | "
                f"[{_pp(measure['ci95']['low'])}, {_pp(measure['ci95']['high'])}] | "
                f"{correction['p_two_sided']:.4f} | {correction['holm_adjusted_p']:.4f} |")
        lines += ["", "CI 按域内结构簇分层重采样；两个预设终点用 Holm 校正。"
            "统计量条件于这些已冻结历史；变体、历史别名和缓存复用不增加独立样本数。"
            "未见域只有 4 个结构家族：双侧精确 sign-flip 的最小 p 为 2/2⁴ = 0.125，"
            "所以无论观测效应多大，本设计均不能在 0.05 水平确认 Rule 增益；这里只估计方向与幅度。"
            "macro 有 12 个结构家族，可取得更小的 p。区间跨零不等于没有效果，也不证明无害。", "",
            "### 配对 gain/loss 与不可评", "",
            "| 比较（前者−后者） | win | loss | tie | 任一不可评 | 可评失败损失 | 交付失败损失 | 已交付但不可评损失 |",
            "|---|---:|---:|---:|---:|---:|---:|---:|"]
        for key, comparison in summary["comparisons"].items():
            c = comparison["counts"]
            columns = [str(c[k]) for k in ("wins", "losses", "ties", "paired_unknown",
                "confirmed_semantic_losses", "delivery_losses", "delivered_oracle_unknown_losses")]
            lines.append("| " + key + " | " + " | ".join(columns) + " |")
        lines += ["", "这些是相关的策略位置计数，不是独立试验数；不可评可与 win/loss 重叠。"
            "可评失败也可能包含运行异常，不能把全部 loss 解释为纯推理错误或 Skill 机制毒害。", ""]
    lines += ["## 全部候选与选择结果", "",
        "| 更新臂 | 候选次数 | 有效文本 | 改变父 Skill | selection 接受 |",
        "|---|---:|---:|---:|---:|"]
    for arm in protocol["learning_arms"]:
        rows = [r for r in proposals if r["arm"] == arm]
        lines.append(f"| {arm} | {len(rows)} | {sum(r['valid'] for r in rows)} | "
                     f"{sum(r['changed'] for r in rows)} | {sum(r['accepted'] for r in rows)} |")
    lines += ["", f"包含全部 {len(proposals)} 次候选更新，不挑选有利历史。"
        "selection 仅在新的同开发域小切片上严格提升时替换诊断部署文本；"
        "不改变 raw 进化父链，也不是跨域安全认证。", ""]
    ledger = result["ledger"]
    lines += ["## 实际消耗与审计", "",
        f"逻辑调用 {ledger['cached_logical_calls']}/{ledger['max_logical_calls']}；"
        f"HTTP 尝试 {ledger['http_attempts_from_cached_records']}；成功调用 {ledger['successful_calls']}；"
        f"终止错误 {ledger['terminal_errors']}。",
        f"账本记录输入 token {ledger['prompt_tokens']}，输出 token {ledger['completion_tokens']}，"
        f"总 token {ledger['total_tokens']}；{ledger['missing_usage_calls']} 次缺少 usage。"
        "缺失 usage 不视作真实零消耗；不根据未核实价格估算费用。", "",
        f"完整回放核对 {audit['verified_run_files']} 个已有文件，实验目录内容不变；"
        "报告阶段模型调用 0、原生代码执行 0。只在 docs 新建不可变报告。",
        "稳定证据摘要仅排除根级 supervisor.log（运行调度日志）；"
        "回放前后的逐文件字节一致性检查仍包含该日志，科学回执不作任何排除。",
        f"结果摘要：{result['record_hash']}。审计摘要：{audit['record_hash']}。", "",
        "## 能说明什么与下一步", "",
        "这是原创合成任务上的探索性内容进化实验，不是公开 benchmark 复现；两个自写更新器均非原生 SkillOpt。"
        "当前对比不能分离配对证据与对照指令的贡献，也没有测量 DeepResearch 或 Rubric 协同进化的独立贡献。"
        "只有两个开发域及一个未见域，且没有独立预注册的 near-miss 任务组；不能宣称安全认证、非劣效或全面跨域泛化。",
        "下一步应冻结本次结论与所有候选，在新任务/显著更多独立结构家族及公开 benchmark 上验证；"
        "单纯增加同家族变体或共享轨迹重复，不能弥补未见域检验的分辨率限制。"
        "若引入 Research/Rubric，应增加等预算的独立消融，而非用 selected 的最好结果替代 raw 主比较。", ""]
    return "\n".join(lines)


def report(output, report_path, *, repo=REPO):
    repo = Path(repo).resolve()
    root = study.safe_root(repo, output)
    if not (root / "results.json").is_file() or not (root / ".run.lock").is_file():
        raise ValueError("Completed result and pre-existing run lock are required")
    with (root / ".run.lock").open("rb") as handle:
        fcntl.flock(handle, fcntl.LOCK_SH | fcntl.LOCK_NB)
        before = _tree(root)
        protocol, result = study.read(root / "protocol.json"), study.read(root / "results.json")
        if result.get("complete") is not True or result.get("protocol_hash") != protocol["record_hash"]:
            raise ValueError("Complete result/protocol binding is required")
        target = _target(report_path, repo, root, protocol)
        replay = study.Study(repo, root, design=protocol["design"], api_factory=_forbidden)
        if not replay.complete:
            raise ValueError("Report cannot start or resume an incomplete experiment")
        with ExitStack() as stack:
            stack.enter_context(patch.object(runtime.legacy, "evaluate", _forbidden))
            stack.enter_context(patch.object(study.OfflineAPI, "call", _forbidden))
            stack.enter_context(redirect_stdout(StringIO()))
            replayed = replay.run()
        if replayed != result or study.read(root / "results.json") != result or _tree(root) != before:
            raise ValueError("Completed replay differs or changed experiment files")
        proposals = _learning_rows(root, protocol, result)
        stable_evidence = {path: value for path, value in before.items() if path != "supervisor.log"}
        audit = seal({"version": "v12-report-completed-readonly-audit-v1",
            "result_hash": result["record_hash"], "protocol_hash": protocol["record_hash"],
            "verified_run_files": len(before),
            "run_files_hash": hashlib.sha256(json.dumps(stable_evidence, sort_keys=True).encode()).hexdigest(),
            "operational_log_exclusions": ["supervisor.log"],
            "replay_byte_equality_includes_operational_logs": True,
            "model_api_calls": 0, "native_executions": 0, "run_files_unchanged": True})
        content = render(protocol, result, audit, proposals)
        if study.source_hashes(repo) != protocol["source_hashes"] or _tree(root) != before:
            raise ValueError("Frozen sources/evidence changed before report publication")
        existed = target.exists()
        write_immutable_text(target, content)
    return {"report": str(target), "created": not existed, "result_hash": result["record_hash"],
            "report_sha256": hashlib.sha256(content.encode()).hexdigest(),
            "audit_hash": audit["record_hash"], "model_api_calls": 0, "native_executions": 0,
            "run_files_unchanged": True}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args(argv)
    print(json.dumps(report(args.output, args.report), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
