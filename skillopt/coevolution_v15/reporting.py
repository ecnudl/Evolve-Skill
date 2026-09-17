"""Read-only reporting of completed V15 evidence, never a study runner.

No imports of Study, runtime, transport clients, or research retrieval. This
audits sealed record links and recomputes statistics, not artifacts or oracles.
The caller decides whether/where to write the returned Markdown.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from pathlib import Path

from skillopt.coevolution_v5.core import verify

from . import analysis

VERSION = "v15-completed-evidence-report-v1"
ARMS = tuple(p for p in analysis.POLICIES if p != "no_skill")
LABELS = {"no_skill": "No-Skill", "fixed": "固定验证器", "adaptive": "反馈进化验证器",
          "adaptive_research": "反馈＋资料进化验证器", "coding": "Coding",
          "spreadsheet": "Spreadsheet", "rule_reasoning": "Rule"}


def _read(path):
    path = Path(path)
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError("Symlink report evidence is forbidden")
    if not path.is_file():
        raise ValueError("Missing completed evidence: " + path.name)
    return verify(json.loads(path.read_text(encoding="utf-8")))


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _records(root, directory):
    location = root / directory
    _require(not location.is_symlink(), "Symlink evidence directory")
    return [_read(p) for p in sorted(location.glob("*.json"))]


def _hash_set(records, hashes, label):
    actual = [r["record_hash"] for r in records]
    _require(isinstance(hashes, list) and len(set(hashes)) == len(hashes)
             and len(set(actual)) == len(actual) and set(actual) == set(hashes),
             label + " record inventory differs from frozen hashes")


def _metadata(tasks):
    result = {}
    for task in tasks:
        _require(isinstance(task, dict) and task.get("id") not in result, "Duplicate/malformed task")
        result[task["id"]] = {"domain": task.get("domain", "coding"), "cluster_id": task["cluster_id"]}
    return result


def _identity(record):
    identity = record["identity"]
    match = re.fullmatch(r"h(\d+)-r(\d+)-(adaptive|adaptive_research)", identity.get("key", ""))
    _require(match is not None, "Unrecognized validator history/round/arm identity")
    h, r, arm = int(match[1]), int(match[2]), match[3]
    _require(identity.get("repeat") == h, "Validator repeat differs from history")
    return h, r, arm


def _calibration_counts(record, expected, old_state, new_state, control_sizes):
    """Check known schema, retaining natural diagnostics separately from controls."""
    roles = record.get("rows")
    natural = record.get("natural_rows")
    _require(isinstance(roles, dict) and set(roles) == {"old", "new"}
             and isinstance(natural, dict) and set(natural) == {"old", "new"},
             "Unknown calibration schema; refuse to invent calibration metrics")
    names = {"reference": "good", "equivalent": "good", "semantic_mutant": "bad",
             "preservation_mutant": "bad"}
    wanted = {(task, name) for task in expected for name in names}
    indexed, metrics, native = {}, {}, {}
    for role in ("old", "new"):
        index = {}
        for row in roles[role]:
            key = row["task_id"], row["artifact"]
            _require(key not in index and key in wanted and row["truth"] == names[key[1]],
                     "Calibration control grid or truth label differs")
            _require(row["domain"] == expected[key[0]]["domain"], "Calibration domain differs")
            assessment = verify(row["assessment"])
            outcome = assessment["outcome"]
            _require(outcome in {"detected", "not_detected", "unknown"}, "Unknown assessment outcome")
            index[key] = row
        _require(set(index) == wanted, "Incomplete calibration control grid")
        indexed[role] = index
        counts = Counter((row["truth"], row["assessment"]["outcome"]) for row in index.values())
        metrics[role] = {"true_detections": counts["bad", "detected"],
            "false_rejections": counts["good", "detected"],
            "unknown": counts["good", "unknown"] + counts["bad", "unknown"],
            "good_unknown": counts["good", "unknown"], "bad_total": len(expected) * 2,
            "good_total": len(expected) * 2}
        natural_index = {}
        for row in natural[role]:
            task = row["task_id"]
            _require(task in expected and task not in natural_index and row.get("used_for_gate") is False,
                     "Natural calibration observations are duplicate, missing, or used for gate")
            _require(row["domain"] == expected[task]["domain"], "Natural calibration domain differs")
            outcome = verify(row["assessment"])["outcome"]
            _require(outcome in {"detected", "not_detected", "unknown"}, "Unknown natural outcome")
            _require(record["identity"]["natural_hashes"].get(task) == row["source_solve_hash"],
                     "Natural artifact source does not match calibration identity")
            natural_index[task] = row
        _require(set(natural_index) == set(expected), "Incomplete natural calibration panel")
        native[role] = natural_index
    _require(record.get("metrics") == metrics, "Stored calibration metrics differ from control rows")
    gains = losses = 0
    for key in wanted:
        a, b = indexed["old"][key], indexed["new"][key]
        if a["truth"] == "bad":
            gains += a["assessment"]["outcome"] != "detected" and b["assessment"]["outcome"] == "detected"
            losses += a["assessment"]["outcome"] == "detected" and b["assessment"]["outcome"] != "detected"
    ngain = nloss = 0
    for task in expected:
        a, b = native["old"][task], native["new"][task]
        _require(a["source_solve_hash"] == b["source_solve_hash"] and a["ordinary_score"] == b["ordinary_score"],
                 "Natural old/new comparison does not share the same artifact")
        ngain += a["assessment"]["outcome"] != "detected" and b["assessment"]["outcome"] == "detected"
        nloss += a["assessment"]["outcome"] == "detected" and b["assessment"]["outcome"] != "detected"
    _require((record.get("paired_true_detection_gains"), record.get("paired_true_detection_losses"),
              record.get("natural_detection_gains"), record.get("natural_detection_losses")) ==
             (gains, losses, ngain, nloss), "Stored paired calibration counts differ")
    canonical = record.get("canonical_controls", [])
    canonical_wanted = {(task, name, offset) for task in expected for name in names
                        for offset in range(0, control_sizes[task], 4)}
    ckeys = [(r["task_id"], r["artifact"], r["input_offset"]) for r in canonical]
    _require(len(ckeys) == len(canonical_wanted) and set(ckeys) == canonical_wanted,
             "Incomplete canonical control grid")
    grouped = {}
    for row in canonical:
        _require(row["truth"] == names[row["artifact"]], "Canonical control truth changed")
        outcome = verify(row["assessment"])["outcome"]
        _require(outcome in {"detected", "not_detected", "unknown"}, "Unknown canonical outcome")
        grouped.setdefault((row["task_id"], row["artifact"], row["truth"]), []).append(outcome)
    canonical_valid = all("unknown" not in outcomes and (
        all(x == "not_detected" for x in outcomes) if truth == "good" else "detected" in outcomes)
        for (_, _, truth), outcomes in grouped.items())
    _require(record.get("canonical_valid") is canonical_valid, "Canonical validity differs")
    old, new = metrics["old"], metrics["new"]
    policy_changed = any(new_state[k] != old_state[k] for k in ("search_policy", "when"))
    _require(record.get("policy_changed") is policy_changed, "Policy text-change flag differs")
    accepted = (canonical_valid and policy_changed
        and new["true_detections"] > old["true_detections"] and new["false_rejections"] == 0
        and new["unknown"] <= old["unknown"] and new["good_unknown"] <= old["good_unknown"] and losses == 0)
    _require(record.get("accepted") is accepted and record.get("natural_labels_used_for_gate") is False,
             "Calibration admission differs from frozen descriptive criteria")
    return {"metrics": metrics, "natural_gains": ngain, "natural_losses": nloss,
            "natural_positions_per_role": len(expected),
            "natural_artifact_hashes": {r["source_solve_hash"] for r in native["old"].values()}}


def _audit(root):
    result = _read(root / "results.json")
    _require(result.get("complete") is True, "Only completed runs can be reported")
    protocol, panel = _read(root / "protocol.json"), _read(root / "private_panel.json")
    frozen, grid = _read(root / "final_frozen.json"), _read(root / "final_rows.json")
    checkpoint_grid = _read(root / "checkpoint_rows.json")
    snapshot = _read(root / "source_snapshot.json")
    _require(result["protocol_hash"] == frozen["protocol_hash"] == protocol["record_hash"], "Protocol link differs")
    _require(result["frozen_hash"] == grid["frozen_hash"] == checkpoint_grid["frozen_hash"] == frozen["record_hash"],
             "Final freeze link differs")
    _require(result["final_grid_hash"] == grid["record_hash"]
             and result["checkpoint_grid_hash"] == checkpoint_grid["record_hash"], "Final grid link differs")
    _require(protocol["panel_hash"] == panel["record_hash"]
             and protocol["source_snapshot_hash"] == snapshot["record_hash"], "Panel/source link differs")
    if protocol.get("task_preflight_hash") is not None:
        checked = _read(root / "task_preflight.json")
        _require(checked["record_hash"] == protocol["task_preflight_hash"] and checked.get("all_checked") is True,
                 "Task preflight link or validity differs")
    sources = {name: hashlib.sha256(text.encode()).hexdigest() for name, text in snapshot["files"].items()}
    _require(sources == protocol["source_hashes"], "Source snapshot content hashes differ")
    for name, path in (("analysis", Path(analysis.__file__)), ("reporting", Path(__file__))):
        relative = "skillopt/coevolution_v15/" + name + ".py"
        _require(sources.get(relative) == hashlib.sha256(path.read_bytes()).hexdigest(), "Analysis/report source drift")
    _require(protocol.get("policies") == list(analysis.POLICIES), "Policy design differs")
    _require(protocol.get("design") == result.get("design") and result["design"] in {"smoke", "pilot"}, "Design differs")
    _require(protocol.get("final_validator_online_assistance") is False
             and protocol.get("all_checkpoints_frozen_before_any_final") is True
             and protocol.get("scope_promotion") is False
             and protocol.get("skill_selection_or_routing") is False,
             "Report does not describe this experimental intervention")
    histories, rounds = protocol["histories"], protocol["rounds"]
    _require(type(histories) is int and 1 <= histories <= 100 and type(rounds) is int and 2 <= rounds <= 20,
             "Invalid history/round count")
    groups = panel["groups"]
    _require(set(groups) == {"train", "calibration", "final"}
             and len(groups["train"]) == rounds and len(groups["calibration"]) == rounds - 1, "Panel partitions differ")
    flattened = {k: (v if k == "final" else [task for batch in v for task in batch]) for k, v in groups.items()}
    metas = {k: _metadata(v) for k, v in flattened.items()}
    _require(protocol["split_counts"] == {k: len(v) for k, v in metas.items()}, "Task counts differ")
    all_ids = [t for v in metas.values() for t in v]
    _require(len(set(all_ids)) == len(all_ids), "Task leakage across partitions")
    family_sets = {k: {m["cluster_id"] for m in v.values()} for k, v in metas.items()}
    _require(all(not family_sets[a] & family_sets[b] for a, b in
                 (("train", "calibration"), ("train", "final"), ("calibration", "final"))), "Family leakage across partitions")
    _require(all(m["domain"] != "rule_reasoning" for k in ("train", "calibration") for m in metas[k].values()),
             "Rule domain entered development")
    summary = analysis.summarize(grid["rows"], policies=analysis.POLICIES,
        expected_tasks=metas["final"], expected_histories=list(range(histories)))
    _require(summary == verify(result["summary"]), "Stored final summary differs from paired native grid")
    _require(all(row.get("round") == rounds - 1 and row.get("phase") == "final" for row in grid["rows"]),
             "Wrong final checkpoint")
    checkpoints = _records(root, "checkpoints")
    _hash_set(checkpoints, frozen["checkpoint_hashes"], "Checkpoint")
    _require(len(checkpoints) == rounds and {c["round"] for c in checkpoints} == set(range(rounds)), "Checkpoint grid differs")
    checkpoints = {c["round"]: c for c in checkpoints}
    _require([checkpoints[r]["record_hash"] for r in range(rounds)] == frozen["checkpoint_hashes"], "Checkpoint order differs")
    for checkpoint in checkpoints.values():
        _require(len(checkpoint["skills"]) == len(checkpoint["validators_for_next_round"]) == histories, "History state grid differs")
        for s, v in zip(checkpoint["skills"], checkpoint["validators_for_next_round"]):
            _require(set(s) == set(v) == set(ARMS), "Checkpoint arm grid differs")
            for state in v.values():
                verify(state)
    _require(frozen["skills"] == checkpoints[rounds - 1]["skills"]
             and frozen["validators"] == checkpoints[rounds - 1]["validators_for_next_round"], "Final state differs from checkpoint")
    updates = _records(root, "learning")
    _hash_set(updates, frozen["skill_update_hashes"], "Learning")
    ui = {(u["history"], u["round"], u["arm"]): u for u in updates}
    expected_updates = {(h, r, a) for h in range(histories) for r in range(rounds) for a in ARMS}
    _require(len(updates) == len(ui) and set(ui) == expected_updates, "Learning update grid differs")
    for (h, r, arm), update in ui.items():
        parent = "" if r == 0 else checkpoints[r - 1]["skills"][h][arm]["skill"]
        current = checkpoints[r]["skills"][h][arm]
        _require(update["parent_hash"] == hashlib.sha256(parent.encode()).hexdigest()
                 and update["state"] == current and update["skill"] == current["skill"]
                 and update["skill_hash"] == hashlib.sha256(current["skill"].encode()).hexdigest(), "Skill lineage differs")
        _require(type(update["valid"]) is bool and update["changed"] is (parent != current["skill"])
                 and update.get("calibration_or_final_feedback_used") is False, "Learning status/leakage flags differ")
    for r, checkpoint in checkpoints.items():
        _hash_set([u for u in updates if u["round"] <= r], checkpoint["completed_updates"], "Checkpoint learning")
    expected_learning = {"update_positions": len(updates), "valid": sum(u["valid"] for u in updates),
        "changed": sum(u["changed"] for u in updates), "unique_update_calls": len({u["request_hash"] for u in updates})}
    _require(result["learning"] == expected_learning, "Learning aggregate differs")
    for row in grid["rows"]:
        skill = "" if row["policy"] == "no_skill" else frozen["skills"][row["history"]][row["policy"]]["skill"]
        _require(row["skill_hash"] == hashlib.sha256(skill.encode()).hexdigest(), "Final row did not use its frozen Skill")
    proposals, calibrations = _records(root, "validator/proposals"), _records(root, "validator/calibrations")
    _hash_set(proposals, frozen["validator_proposal_hashes"], "Validator proposal")
    _hash_set(calibrations, frozen["calibration_hashes"], "Calibration")
    pi, ci = {_identity(p): p for p in proposals}, {_identity(c): c for c in calibrations}
    wanted = {(h, r, a) for h in range(histories) for r in range(rounds - 1) for a in ARMS if a != "fixed"}
    _require(len(pi) == len(proposals) and set(pi) == wanted, "Validator proposal grid differs")
    _require(len(ci) == len(calibrations) and set(ci) == {k for k, p in pi.items() if p["valid"]}, "Calibration admission grid differs")
    calibration_views = {}
    for (h, r, arm), proposal in pi.items():
        initial = checkpoints[0]["validators_for_next_round"][h]["fixed"]
        old = initial if r == 0 else checkpoints[r - 1]["validators_for_next_round"][h][arm]
        _require(proposal["arm"] == arm and type(proposal["valid"]) is bool
                 and proposal["parent_state_hash"] == proposal["identity"]["parent_hash"] == old["record_hash"],
                 "Validator proposal lineage differs")
        candidate = verify(proposal["candidate_state"])
        accepted = old
        if proposal["valid"]:
            calibration = ci[h, r, arm]
            _require(calibration["identity"]["old_hash"] == old["record_hash"]
                     and calibration["identity"]["new_hash"] == candidate["record_hash"]
                     and calibration["activation"] == "next_round_only", "Calibration policy/activation link differs")
            calibration_tasks = groups["calibration"][r]
            control_sizes = {t["id"]: len(t["public_cases"]) + len(t[
                "private_cases" if t.get("domain", "coding") == "coding" else "hidden_cases"])
                for t in calibration_tasks}
            _require(all(1 <= count <= 32 for count in control_sizes.values()), "Invalid ordinary control size")
            calibration_views[h, r, arm] = _calibration_counts(
                calibration, _metadata(calibration_tasks), old, candidate, control_sizes)
            accepted = candidate if calibration["accepted"] else old
            _require(verify(calibration["accepted_state"]) == accepted, "Accepted validator state differs")
        _require(checkpoints[r]["validators_for_next_round"][h][arm] == accepted, "Validator activated in the wrong round")
    for h in range(histories):
        initial = checkpoints[0]["validators_for_next_round"][h]["fixed"]
        for r in range(rounds):
            _require(checkpoints[r]["validators_for_next_round"][h]["fixed"] == initial, "Fixed validator changed")
        _require(checkpoints[rounds - 1]["validators_for_next_round"][h] ==
                 checkpoints[rounds - 2]["validators_for_next_round"][h], "Validator changed after its final opportunity")
    expected_validator = {"proposals": len(proposals), "valid_proposals": sum(p["valid"] for p in proposals),
                         "calibrations": len(calibrations), "accepted": sum(c["accepted"] for c in calibrations)}
    _require(result["validator_evolution"] == expected_validator, "Validator aggregate differs")
    audit_ids = [t["id"] for domain in ("coding", "spreadsheet")
                 for t in [t for t in groups["final"] if t.get("domain", "coding") == domain][:2]]
    audit_meta = {t: metas["final"][t] for t in audit_ids}
    _require(checkpoint_grid.get("diagnostic_subset_only") is True and checkpoint_grid.get("feedback_allowed") is False,
             "Checkpoint diagnostics cannot influence learning")
    _require({row.get("round") for row in checkpoint_grid["rows"]} == set(range(rounds)), "Missing checkpoint audit round")
    curves = {}
    for r in range(rounds):
        rrows = [row for row in checkpoint_grid["rows"] if row["round"] == r]
        curves[r] = analysis.summarize(rrows, policies=analysis.POLICIES, expected_tasks=audit_meta,
                                      expected_histories=list(range(histories)))
        for row in rrows:
            text = "" if row["policy"] == "no_skill" else checkpoints[r]["skills"][row["history"]][row["policy"]]["skill"]
            _require(row["skill_hash"] == hashlib.sha256(text.encode()).hexdigest(), "Checkpoint row Skill differs")
    final_subset = {(r["task_id"], r["history"], r["policy"]): r for r in grid["rows"] if r["task_id"] in audit_meta}
    _require({(r["task_id"], r["history"], r["policy"]): r for r in checkpoint_grid["rows"] if r["round"] == rounds - 1}
             == final_subset, "Last checkpoint is not the exact final-row subset")
    return result, protocol, summary, updates, pi, ci, calibration_views, curves


def _percent(value):
    return "N/A" if value is None else f"{100 * value:.2f}%"


def _delta(value):
    return f"{100 * value:+.2f}"


def render(root) -> str:
    """Return concise Chinese Markdown after read-only, fail-closed auditing."""
    root = Path(root).absolute()
    result, protocol, summary, updates, proposals, calibrations, views, curves = _audit(root)
    smoke = result["design"] == "smoke"
    lines = ["# V15 协同进化实验报告", "", f"状态：已完成；设计：{'smoke（工程冒烟）' if smoke else 'pilot（探索性实验）'}。"]
    if smoke:
        lines += ["", "**Smoke 仅检查链路，不提供方法有效性或泛化结论。**"]
    lines += ["", "所有条件共用求解器、结构化反馈和全文 Skill 更新器。fixed 的验证器保持不变；"
        "adaptive 根据开发证据修订测试输入搜索策略；adaptive_research 另使用限定官方资料。"
        "合法提案经过独立校准，接受后下一轮生效；最后冻结全部 Skill/checkpoint，再进行原生最终评测。",
        "", "本轮研究的是冻结后的 raw Skill 内容，不是路由、scope 扩张、原版 SkillOpt 对照或公开 benchmark。"
        "最终求解不接受在线验证器辅助；Rule 未进入开发或校准。", "", "## 最终成绩", ""]
    domains = [d for d in ("coding", "spreadsheet", "rule_reasoning") if d in summary["domains"]]
    domains += [d for d in summary["domains"] if d not in domains]
    lines += ["| 条件 | " + " | ".join(LABELS.get(d, d) for d in domains) + " | 域等权 Macro | 未知 / 总位置 |",
              "|---|" + "---:|" * (len(domains) + 2)]
    for policy in analysis.POLICIES:
        row = summary["policy_summary"][policy]
        lines.append("| " + LABELS[policy] + " | " + " | ".join(_percent(row["by_domain"][d]["all_attempt_success"]) for d in domains)
                     + f" | {_percent(row['macro_all_attempt_success'])} | {row['oracle_unknown']}/{row['total']} |")
    lines += ["", "分母保留所有尝试；API、交付与 oracle unknown 不删除，也不混称为语义失败。", "",
              "| 配对比较 | Macro 差值 [95% CI]，pp | 最差领域差值，pp | 赢 / 输 |", "|---|---:|---:|---:|"]
    for key in ("adaptive_vs_fixed", "adaptive_research_vs_adaptive", "fixed_vs_no_skill",
                "adaptive_vs_no_skill", "adaptive_research_vs_no_skill"):
        row = summary["comparisons"][key]
        interval = row["macro"]["ci95"]
        lines.append(f"| {LABELS[row['candidate']]} − {LABELS[row['reference']]} | {_delta(row['macro']['delta'])} "
                     f"[{_delta(interval[0])}, {_delta(interval[1])}] | {_delta(row['worst_domain_delta'])} | "
                     f"{row['counts']['wins']} / {row['counts']['losses']} |")
    families = "、".join(f"{LABELS.get(d, d)} {summary['structural_families_by_domain'][d]} 族" for d in domains)
    lines += ["", f"样本：{summary['task_instances']} 个任务；{families}；{len(summary['histories'])} 条冻结历史。"
        "区间按域内结构族整体重采样，保留全部历史，仅条件于本轮冻结历史；重复、别名响应和 checkpoint 不增加独立样本数。"
        "区间未作多重比较控制；小样本、零宽区间或未观察到退化均不证明显著优越、等效或安全。", "", "## 进化实际发生了什么", ""]
    lr, vr = result["learning"], result["validator_evolution"]
    lines += [f"Skill 更新：{lr['valid']}/{lr['update_positions']} 个位置合法，{lr['changed']} 个改变文字，"
              f"{lr['unique_update_calls']} 次独立请求身份（不等于独立训练样本）。",
              f"验证器：{vr['valid_proposals']}/{vr['proposals']} 个合法提案，{vr['calibrations']} 次校准，{vr['accepted']} 次接受。",
              "", "| 提案轮次 | 条件 | 合法 / 提案 | 接受 / 校准 |", "|---|---|---:|---:|"]
    for r in range(protocol["rounds"] - 1):
        for arm in ARMS[1:]:
            ps = [p for (h, round_index, a), p in proposals.items() if round_index == r and a == arm]
            cs = [c for (h, round_index, a), c in calibrations.items() if round_index == r and a == arm]
            lines.append(f"| {r + 1} | {LABELS[arm]} | {sum(p['valid'] for p in ps)}/{len(ps)} | {sum(c['accepted'] for c in cs)}/{len(cs)} |")
    if not vr["accepted"]:
        lines += ["", "**没有验证器被激活：即使最终分数提高，也不能据此声称验证器—Skill 协同进化有效。**"]
    lines += ["", "人工控制校准与自然产物诊断分开统计（下列均为评价位置，不是独立任务数）：", "",
              "| 条件 | 人工缺陷检出 old→new | 正确控制误拒 old→new | unknown old→new | 自然检测新增 / 丢失 |", "|---|---:|---:|---:|---:|"]
    for arm in ARMS[1:]:
        selected = [v for (h, r, a), v in views.items() if a == arm]
        def total(role, field):
            return sum(v["metrics"][role][field] for v in selected)
        lines.append(f"| {LABELS[arm]} | {total('old', 'true_detections')}→{total('new', 'true_detections')} | "
                     f"{total('old', 'false_rejections')}→{total('new', 'false_rejections')} | "
                     f"{total('old', 'unknown')}→{total('new', 'unknown')} | "
                     f"{sum(v['natural_gains'] for v in selected)} / {sum(v['natural_losses'] for v in selected)} |")
    natural_unique = {h for v in views.values() for h in v["natural_artifact_hashes"]}
    lines += ["", f"自然校准复用 {len(natural_unique)} 个 No-Skill 产物：未发现反例不等于正确，"
        "新增检测不自动等于检错率提升；自然结果不参与接收门，也不回流 Skill updater。"
        "人工 reference/equivalent/mutant 校准通过不是自然部署安全证明。资料是有界检索，不是自主开放式 DeepResearch；引用匹配不是蕴含认证。",
        "", "第二轮共同父版本检查（r=1，从零编号）：", "", "| 历史 | 三臂父 Skill 相同 | 反馈 hash 种类 | 请求 hash 种类 |", "|---|---|---:|---:|"]
    for h in summary["histories"]:
        group = [u for u in updates if u["history"] == h and u["round"] == 1]
        lines.append(f"| {h} | {'是' if len({u['parent_hash'] for u in group}) == 1 else '否'} | "
                     f"{len({u['feedback_hash'] for u in group})} | {len({u['request_hash'] for u in group})} |")
    lines += ["", "共同父版本仅帮助描述早期分支差异；后续父版本分化后不能当成同一父版本的单因素效果。", "",
              "## 冻结 checkpoint 小面板诊断", "", "仅 Coding/Spreadsheet 每域前两族（smoke 以实际数量为准）；"
              "全部版本冻结后才评测，不参与选择或反馈，不能当作额外最终样本。", "",
              "| 更新后轮次 | No-Skill | 固定验证器 | 反馈进化 | 反馈＋资料 |", "|---|---:|---:|---:|---:|"]
    for r, curve in sorted(curves.items()):
        lines.append(f"| {r + 1} | " + " | ".join(_percent(curve["policy_summary"][p]["macro_all_attempt_success"])
                                                        for p in analysis.POLICIES) + " |")
    ledger = result["ledger"]
    lines += ["", "## 成本与限制", "",
        f"逻辑调用 {ledger['cached_logical_calls']}，HTTP 尝试 {ledger['http_attempts_from_cached_records']}，"
        f"终止不可用 {ledger['terminal_errors']}；已记录输入/输出/总 tokens："
        f"{ledger['prompt_tokens']}/{ledger['completion_tokens']}/{ledger['total_tokens']}。"
        f"{ledger['missing_usage_calls']} 次缺失 usage，不能按零成本处理。",
        "相同 solver/updater/probe 机会不等于相同总计算量；额外提案、校准、资料与反馈长度均有成本。"
        "本报告只读校验哈希链并重算统计，没有 API 请求、产物执行或事后重评分；哈希一致不证明 oracle 完备或任务族独立。",
        "", f"结果 hash：`{result['record_hash']}`。", f"报告版本：`{VERSION}`。", ""]
    return "\n".join(lines)
