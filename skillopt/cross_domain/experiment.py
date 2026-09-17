"""Preregistered, resumable synthetic scope-evolution experiment orchestration."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from collections import defaultdict
from pathlib import Path

import numpy as np

from skillopt.cross_domain.evolution import generate_candidates
from skillopt.cross_domain.gate import decide_scope, pair_stats
from skillopt.cross_domain.policies import (
    fit_scope_groups,
    mask_from_scope,
    matched_coverage_masks,
    paired_rows,
    partition_validation,
    propose_mechanism_scopes,
    route_inputs,
    route_labels,
)
from skillopt.cross_domain.runtime import CachedAPI, configure_api, digest, read_json, rollout, write_json
from skillopt.cross_domain.tasks import build_tasks


def _code_hashes(repo):
    return {str(p.relative_to(repo)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted((repo / "skillopt/cross_domain").glob("*.py"))}


def prepare(repo, root, protocol, provider):
    generator = repo / "skillopt/cross_domain/tasks.py"
    manifest = {"protocol": protocol, "provider": provider,
                "generator_sha256": hashlib.sha256(generator.read_bytes()).hexdigest(),
                "git_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()}
    path = root / "protocol.json"
    if path.exists() and read_json(path) != manifest:
        raise ValueError("Run protocol/provider/generator changed; use a new out directory")
    write_json(path, manifest)
    return manifest


def dataset(root, protocol, split):
    tasks = build_tasks(seed=protocol["seed"], split=split, n_per_cell=protocol[f"{split}_per_cell"])
    values = [t.to_dict() for t in tasks]
    path = root / "datasets" / f"{split}.json"
    if path.exists() and digest(read_json(path)) != digest(values):
        raise ValueError("Task data changed on resume")
    write_json(path, values)
    return tasks


def _mean(rows):
    valid = [r for r in rows if r["agent_ok"]]
    return sum(r["hard"] for r in valid) / len(valid) if valid else None


def pilot(api, protocol):
    result = {}
    for split in ("train", "dev"):
        tasks = dataset(api.root, protocol, split)
        rows = rollout(api, tasks, "", f"pilot_{split}")
        cells = defaultdict(list)
        for row in rows:
            cells[row["mechanism"] + "/" + row["group"]].append(row)
        result[split] = {"n": len(rows), "em": _mean(rows),
                         "api_errors": sum(not r["agent_ok"] for r in rows),
                         "cells": {key: {"n": len(value), "em": _mean(value)} for key,value in cells.items()}}
    write_json(api.root / "pilot_summary.json", result)
    return result


def _outcomes(api, tasks, skills, label, repeat=0):
    baseline = rollout(api, tasks, "", label + "_base", repeat)
    results = {}
    for skill in skills:
        candidate = rollout(api, tasks, skill["content"], label + "_" + skill["id"], repeat)
        current = (rollout(api, tasks, skill["parent_content"], label + "_parent_" + skill["id"], repeat)
                   if skill["parent_content"] else baseline)
        results[skill["id"]] = (baseline, current, candidate)
    return results


def _complete(rows, expected):
    if len(rows) != expected:
        raise RuntimeError("API failure in calibration/confirmation: cannot certify using missing rows")


def validate(api, protocol, repo):
    frozen_path = api.root / "frozen_policies.json"
    if frozen_path.exists():
        frozen = read_json(frozen_path)
        if frozen["code_hashes"] != _code_hashes(repo):
            raise ValueError("Frozen experiment code changed before test; refuse silent resume")
        return frozen
    candidates = read_json(api.root / "candidates.json")
    skills = propose_mechanism_scopes(api, candidates["selected"])
    tasks = dataset(api.root, protocol, "validation")
    fit, confirmation = partition_validation(tasks)
    routes = route_inputs(api, tasks, skills, "validation")  # routes before scoring
    outcomes = _outcomes(api, tasks, skills, "validation")
    tracks = {}
    for skill in skills:
        sid = skill["id"]
        base, current, candidate = outcomes[sid]
        labels_fit = route_labels(fit, routes, sid, protocol["router_threshold"], protocol["shuffled_seed"])
        proposals = fit_scope_groups(fit, labels_fit, base, current, candidate, not skill["parent_content"])
        labels_confirm = route_labels(confirmation, routes, sid, protocol["router_threshold"], protocol["shuffled_seed"])
        all_rows = paired_rows(confirmation, base, current, candidate, mechanism=skill["mechanism"],
                               parent_empty=not skill["parent_content"])
        _complete(all_rows, len(confirmation))
        methods = {}
        for method, proposal in proposals.items():
            mask = mask_from_scope(labels_confirm[method], proposal["allowed_groups"])
            rows = paired_rows(confirmation, base, current, candidate, mask=mask,
                               mechanism=skill["mechanism"], parent_empty=not skill["parent_content"])
            _complete(rows, len(confirmation))
            gate_cfg = dict(protocol["gate"])
            # A dev point-estimate accept is NOT a confirmed scope certificate.
            gate_cfg["local_already_committed"] = False
            gate = decide_scope(rows, gate_cfg)
            strict = decide_scope(rows, {**gate_cfg, "noninferiority_margin": .05, "max_conditional_harm": .10})
            # Restriction changes the actual policy. Revalidate it, including
            # non-source items misclassified as coding by the real router.
            local_mask = {t.id: mask[t.id] and routes[t.id]["domain"] == "coding" for t in confirmation}
            local_rows = paired_rows(confirmation, base, current, candidate, mask=local_mask,
                                     mechanism=skill["mechanism"], parent_empty=not skill["parent_content"])
            local_gate = decide_scope(local_rows, gate_cfg)
            local_safe = (local_gate["local_accepted"] and not local_gate["missing_cells"]
                          and all(a["safety"] == "pass" for a in local_gate["group_audits"]))
            mode = ("expanded" if gate["action"] == "cross_domain_commit" else "local" if local_safe else "fallback")
            methods[method] = {**proposal, "confirmation_gate": gate,
                               "local_mask_gate": local_gate,
                               "strict_confirmation_gate": strict, "mode": mode}
            print(f"[gate {sid}/{method}] {gate['action']} -> {mode}, proposed_groups={proposal['allowed_groups']}", flush=True)
        write_json(api.root / "counterexamples" / (sid + ".json"), [r for r in all_rows
                   if (r["baseline"] == 1 or r["current"] == 1) and r["candidate"] == 0])
        tracks[sid] = {"skill": skill, "methods": methods,
                       "forced_confirmation": pair_stats(all_rows)}
    frozen = {"protocol_hash": digest(protocol), "candidates_hash": digest(candidates),
              "validation_hash": digest([t.to_dict() for t in tasks]),
              "fit_ids": [t.id for t in fit], "confirmation_ids": [t.id for t in confirmation],
              "test_accessed": False, "code_hashes": _code_hashes(repo), "tracks": tracks,
              "notes": ["Fit-derived allowed groups confirmed on independent validation partition.",
                        "No test examples, outcomes, or generator mechanism labels entered the router.",
                        "Gate intervals are screening diagnostics, not multiplicity-adjusted universal safety guarantees."]}
    write_json(frozen_path, frozen)
    return frozen


def policy_masks(tasks, routes, track, protocol):
    skill = track["skill"]
    labels = route_labels(tasks, routes, skill["id"], protocol["router_threshold"], protocol["shuffled_seed"])
    masks = {"no_skill": {t.id: False for t in tasks},
             "unconditional": {t.id: True for t in tasks},
             "source_gate": {t.id: skill["accepted_local_point_gate"] for t in tasks}}
    for method, detail in track["methods"].items():
        proposed = mask_from_scope(labels[method], detail["allowed_groups"])
        masks["proposal_" + method] = proposed  # Explicitly uncertified ablation.
        masks["safe_" + method] = {
            t.id: proposed[t.id] and (detail["mode"] == "expanded" or
                                     detail["mode"] == "local" and routes[t.id]["domain"] == "coding")
            for t in tasks}
    for fraction in (.10, .25, .50, .75):
        for method, mask in matched_coverage_masks(tasks, routes, skill, fraction, protocol["shuffled_seed"]).items():
            masks[f"matched_{int(fraction*100)}_{method}"] = mask
    return masks


def summarize_repeats(repeats, expected_ids=None):
    """Cluster bootstrap by original task, not by repeated/duplicated observations."""
    ids = sorted(set.intersection(*(set(r["id"] for r in rows) for rows in repeats)))
    expected = set(expected_ids) if expected_ids is not None else set.union(*(set(r["id"] for r in rows) for rows in repeats))
    if not ids:
        return {"n_unique_tasks": 0, "n_generation_repeats": len(repeats), "baseline_em": None,
                "current_em": None, "em": None, "delta_em": None, "delta_vs_current": None,
                "coverage": None, "improved_observations": 0, "regressed_observations": 0,
                "conditional_harm": None, "delta_bootstrap95": [None, None],
                "repeat_em": [None] * len(repeats), "excluded_tasks_missing_any_repeat": len(expected)}
    lookups = [{r["id"]: r for r in rows} for rows in repeats]
    arrays = {key: np.array([[lookup[tid][key] for lookup in lookups] for tid in ids], dtype=float)
              for key in ("baseline", "current", "candidate", "applied")}
    delta = (arrays["candidate"] - arrays["baseline"]).mean(axis=1)
    rng = np.random.default_rng(42)
    boot = np.array([delta[rng.integers(0, len(ids), len(ids))].mean() for _ in range(4000)]) if ids else np.array([np.nan])
    improved = ((arrays["baseline"] == 0) & (arrays["candidate"] == 1)).sum()
    regressed = ((arrays["baseline"] == 1) & (arrays["candidate"] == 0)).sum()
    base_correct = arrays["baseline"].sum()
    return {"n_unique_tasks": len(ids), "n_generation_repeats": len(repeats),
            "baseline_em": float(arrays["baseline"].mean()), "current_em": float(arrays["current"].mean()),
            "em": float(arrays["candidate"].mean()), "delta_em": float(delta.mean()),
            "delta_vs_current": float((arrays["candidate"]-arrays["current"]).mean()),
            "coverage": float(arrays["applied"].mean()), "improved_observations": int(improved),
            "regressed_observations": int(regressed),
            "conditional_harm": float(regressed/base_correct) if base_correct else None,
            "delta_bootstrap95": [float(v) for v in np.quantile(boot,[.025,.975])],
            "repeat_em": [float(arrays["candidate"][:,i].mean()) for i in range(len(repeats))],
            "excluded_tasks_missing_any_repeat": len(expected)-len(ids)}


def test(api, protocol, repo):
    frozen = read_json(api.root / "frozen_policies.json")
    if frozen["protocol_hash"] != digest(protocol) or frozen["code_hashes"] != _code_hashes(repo):
        raise ValueError("Frozen policy/code mismatch; do not alter experiment after test")
    if frozen["candidates_hash"] != digest(read_json(api.root / "candidates.json")):
        raise ValueError("Frozen candidate mismatch")
    tasks = dataset(api.root, protocol, "test")
    skills = [track["skill"] for track in frozen["tracks"].values()]
    routes = route_inputs(api, tasks, skills, "test")
    masks = {sid: policy_masks(tasks, routes, track, protocol) for sid, track in frozen["tracks"].items()}
    write_json(api.root / "test_masks_before_outcomes.json", masks)
    collected = {sid: defaultdict(list) for sid in masks}
    for repeat in range(protocol["test_repeats"]):
        outcomes = _outcomes(api, tasks, skills, f"test_r{repeat}", repeat)
        for sid, track in frozen["tracks"].items():
            base, current, candidate = outcomes[sid]
            # Use the SAME complete-case set for every policy, even fallback, so
            # failures cannot selectively improve one policy's denominator.
            valid_ids = {r["id"] for r in paired_rows(tasks, base, current, candidate)}
            common = [t for t in tasks if t.id in valid_ids]
            for name, mask in masks[sid].items():
                rows = paired_rows(common, base, current, candidate, mask=mask,
                                   mechanism=track["skill"]["mechanism"],
                                   parent_empty=not track["skill"]["parent_content"])
                collected[sid][name].append(rows)
                write_json(api.root / "policy_outcomes" / sid / f"{name}_r{repeat}.json", rows)
    results = {}
    for sid, policies in collected.items():
        results[sid] = {}
        for name, repeats in policies.items():
            overall = summarize_repeats(repeats, [t.id for t in tasks])
            overall["domains"] = {domain: summarize_repeats([[r for r in rows if r["domain"] == domain] for rows in repeats], [t.id for t in tasks if t.domain == domain])
                                  for domain in ("coding", "spreadsheet", "rule_reasoning")}
            overall["groups"] = {group: summarize_repeats([[r for r in rows if r["group"] == group] for rows in repeats],
                                   [t.id for t in tasks if ("unrelated" if t.group == "positive" and t.mechanism != frozen["tracks"][sid]["skill"]["mechanism"] else t.group) == group])
                                 for group in ("positive", "near_miss", "unrelated")}
            results[sid][name] = overall
    calls = [read_json(p) for p in (api.root / "calls").glob("*.json")]
    usage = {key: sum(r.get("usage",{}).get(key,0) for r in calls) for key in ("prompt_tokens", "completion_tokens", "total_tokens")}
    summary = {"protocol": protocol, "tracks": results, "api_calls": len(calls),
               "api_errors": sum(not r["ok"] for r in calls), "usage": usage,
               "router_errors": sum(not r["ok"] for r in routes.values()),
               "test_tasks": len(tasks), "test_unique_domains": 3, "held_out_domain": "rule_reasoning",
               "evaluation_type": "shared-draw offline policy replay with actual input-only GPT router",
               "training_seeds": [protocol["seed"]], "public_benchmark": False}
    write_json(api.root / "summary.json", summary)
    render_report(api.root, summary, frozen)
    return summary


def render_report(root, summary, frozen):
    def percent(value, precision=2, signed=False):
        if value is None:
            return "N/A"
        return format(100 * value, ("+" if signed else "") + f".{precision}f")

    lines = ["# Cross-Domain Safe Skill Evolution：受控 MVP 实验", "",
             "这是三域合成硬-oracle 诊断，不是公开 benchmark 或真实工具执行能力验证。",
             "仅调用已有 Freerouter GPT-5.5。候选由原 SkillOpt 反思、聚合、排序和补丁引擎产生。",
             "测试采用共享逐题调用的离线策略回放，路由仅看任务输入；不是独立线上策略部署试验。", "",
             f"测试 {summary['test_tasks']} 个唯一任务，每个目标配置 {summary['protocol']['test_repeats']} 次生成；一个训练种子。",
             "rule_reasoning 整域只在冻结后测试；fit/confirmation 独立。测试结果未反馈给候选或阈值。", ""]
    for sid, metrics in summary["tracks"].items():
        lines += [f"## {sid}", "", "| 策略 | EM | 比 Base 增益(pp) | 覆盖率 | 对→错/观测 |", "|---|---:|---:|---:|---:|"]
        for name in ("no_skill", "unconditional", "source_gate", "safe_mechanism", "safe_domain", "safe_shuffled"):
            r = metrics[name]
            lines.append(f"| {name} | {percent(r['em'])}% | {percent(r['delta_em'], signed=True)} | {percent(r['coverage'], 1)}% | {r['regressed_observations']} |")
        lines += ["", "验证门结果："]
        for method, detail in frozen["tracks"][sid]["methods"].items():
            lines.append(f"- {method}: {detail['confirmation_gate']['action']} → {detail['mode']}; scope={detail['allowed_groups']}")
        lines += ["", "### 等覆盖率路由诊断（未经过安全门，不是可部署策略）", "",
                  "| 覆盖率 | 机制路由 EM | Domain 路由 EM | 打乱路由 EM |", "|---|---:|---:|---:|"]
        for pct in (10,25,50,75):
            scores = [percent(metrics[f"matched_{pct}_{m}"]["em"]) for m in ("mechanism","domain","shuffled")]
            lines.append(f"| {pct}% | {scores[0]}% | {scores[1]}% | {scores[2]}% |")
        lines += ["", "各域、正例、Near-Miss、无关任务和按题目聚类 bootstrap 区间见 summary.json。", ""]
    lines += ["## 边界与可复核记录", "",
              "- 若门控全部 fallback，只能说明没有足够证据批准扩张，不能声称方法已经保留收益并减少负迁移。",
              "- 风险区间是固定样本近似检查，未给跨候选、多组、自适应过程或未知域的正式安全保证。",
              "- 主协议非劣容忍10pp、条件退化上限15%，仅用于先导诊断；另保留5pp/10%的严格敏感性结果。",
              "- 两次生成共用训练所得Skill，并非两个训练种子；配对退化不能直接认定确定性的因果伤害。",
              "- API错误不当成模型能力错误；配对策略使用共同成功样本，原始失败保留供审计。",
              "- 实验包含局部提交、跨域提交、限制、拒绝/待证据、反例库和调用前fallback；没有自动Split或DeepResearch。",
              f"- 缓存API调用 {summary['api_calls']}，最终API错误 {summary['api_errors']}；usage={json.dumps(summary['usage'])}。",
              "- protocol.json / candidates.json / frozen_policies.json / datasets / calls / rollouts / routes / counterexamples / policy_outcomes 保存完整证据。", ""]
    (root / "report.md").write_text("\n".join(lines), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="configs/cross_domain/mvp.json")
    parser.add_argument("--out", default="outputs/cross_domain/scope_mvp_gpt55_20260907")
    parser.add_argument("--phase", choices=("pilot","train","validate","test","all"), default="all")
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[2]
    protocol = read_json(repo / args.config)
    root = (repo / args.out).resolve()
    if root == repo or repo not in root.parents:
        raise ValueError("Use a dedicated output directory within the repository")
    provider = configure_api(repo, protocol["model"])
    prepare(repo, root, protocol, provider)
    api = CachedAPI(root, protocol["model"], protocol["workers"])
    if args.phase in {"pilot","all"}:
        print(json.dumps(pilot(api,protocol),ensure_ascii=False), flush=True)
    if args.phase in {"train","all"}:
        generate_candidates(api, dataset(root,protocol,"train"), dataset(root,protocol,"dev"), protocol)
    if args.phase in {"validate","all"}:
        validate(api,protocol,repo)
    if args.phase in {"test","all"}:
        test(api,protocol,repo)
    print(f"[complete] phase={args.phase} output={root}", flush=True)
