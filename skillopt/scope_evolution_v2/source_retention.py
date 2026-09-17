"""Frozen-arm SearchQA source-retention screening and fresh held-out evaluation."""

from __future__ import annotations

import hashlib
import json
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import numpy as np

from skillopt.cross_domain.gate import pair_stats
from skillopt.envs.searchqa.evaluator import evaluate
from skillopt.envs.searchqa.rollout import _build_system, _build_user
from skillopt.scope_evolution_v2.source_data import (
    DEFAULT_CACHE,
    digest,
    file_hash,
    materialize_source_split,
    prepare_source_manifest,
    question_fingerprint,
    read_json,
    write_immutable_json,
    write_immutable_text,
)

BEST_SHA256 = "6aad066e67088cb4d814f8452908f092ca5a9f45ab44fcb7f65deb752fc5d17c"
INITIAL_SHA256 = "d3ed21de4a5216da7c3cd63acc2330dc78227524753c9d29573e6692f48d6709"
DEFAULT_ARMS = ("base", "full", "extractive")


def _write_text_snapshot(path: Path, text: str) -> None:
    write_immutable_text(path, text)


def _code_hashes() -> dict[str, str]:
    repo = Path(__file__).resolve().parents[2]
    names = ["skillopt/scope_evolution_v2/source_data.py", "skillopt/scope_evolution_v2/source_retention.py",
             "scripts/source_retention_mvp.py", "skillopt/envs/searchqa/rollout.py",
             "skillopt/envs/searchqa/evaluator.py", "skillopt/envs/searchqa/prompts/rollout_system.md",
             "skillopt/cross_domain/gate.py", "skillopt/cross_domain/runtime.py",
             "skillopt/model/openai_compatible_backend.py"]
    return {name: file_hash(repo / name) for name in names}


def _skills(repo: Path) -> dict[str, str]:
    full_path = repo / "outputs/repro_searchqa/full_gpt55_seed42/best_skill.md"
    initial_path = repo / "skillopt/envs/searchqa/skills/initial.md"
    if file_hash(full_path) != BEST_SHA256 or file_hash(initial_path) != INITIAL_SHA256:
        raise ValueError("Historical best or initial skill differs from the fixed preregistered SHA256")
    full = full_path.read_text(encoding="utf-8")
    header = "## Extractive / Trivia Evidence Selection"
    if full.count(header) != 1 or "## Jeopardy-Style Wordplay" not in full:
        raise ValueError("Cannot locate the exact extractive evidence section")
    extractive = header + full.split(header, 1)[1].split("## Jeopardy-Style Wordplay", 1)[0]
    return {"base": initial_path.read_text(encoding="utf-8"), "full": full, "extractive": extractive}


def prepare(repo: Path, run_dir: Path, *, arms=DEFAULT_ARMS, workers: int = 6,
            seed: int = 20260908, calibration_n: int = 128, holdout_n: int = 256,
            cache_path: Path = DEFAULT_CACHE) -> dict[str, Any]:
    """Snapshot fixed arms and calibration only; this phase does not configure API."""
    repo, run_dir = Path(repo).resolve(), Path(run_dir).resolve()
    if tuple(arms) not in {("base", "full"), DEFAULT_ARMS} or workers < 1:
        raise ValueError("Use fixed base/full or base/full/extractive arms and positive workers")
    settings = {"arms": list(arms), "workers": workers, "seed": seed,
                "calibration_n": calibration_n, "holdout_n": holdout_n,
                "cache_path": str(Path(cache_path).resolve())}
    protocol_path = run_dir / "source_protocol.json"
    if protocol_path.exists():
        protocol = read_json(protocol_path)
        if protocol["settings"] != settings or protocol["code_hashes"] != _code_hashes():
            raise ValueError("Source protocol/code changed; use a new run directory")
        manifest = read_json(run_dir / "source_manifest.json")
        if digest(manifest) != protocol["manifest_hash"]:
            raise ValueError("Source manifest changed after protocol freeze")
        for arm, info in protocol["arms"].items():
            if file_hash(run_dir / info["snapshot"]) != info["sha256"]:
                raise ValueError(f"Skill snapshot changed: {arm}")
        if file_hash(run_dir / "datasets/calibration.json") != protocol["calibration_data_sha256"]:
            raise ValueError("Calibration payload changed after protocol freeze")
        return protocol
    contents = _skills(repo)
    manifest = prepare_source_manifest(repo, run_dir, seed=seed, calibration_n=calibration_n,
                                       holdout_n=holdout_n, cache_path=cache_path)
    snapshots = {}
    for arm in arms:
        relative = f"skills/{arm}.md"
        _write_text_snapshot(run_dir / relative, contents[arm])
        snapshots[arm] = {"snapshot": relative, "sha256": file_hash(run_dir / relative), "characters": len(contents[arm])}
    calibration = materialize_source_split(manifest, "calibration")
    write_immutable_json(run_dir / "datasets/calibration.json", calibration)
    try:
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True, stderr=subprocess.DEVNULL).strip()
    except subprocess.CalledProcessError:
        commit = "not-a-git-checkout"
    protocol = {
        "protocol_version": "source-retention-v2-1", "settings": settings, "model": "gpt-5.5",
        "backend": "openai_compatible", "required_provider_host": "free-router.opendatalab.com",
        "requested_max_completion_tokens": 16384, "effective_max_tokens_cap": 8000,
        "temperature": "provider default", "reasoning_effort": "not forwarded by compatible backend",
        "generation_seed": "not sent", "git_commit": commit, "code_hashes": _code_hashes(),
        "manifest_hash": digest(manifest), "arms": snapshots,
        "calibration_data_sha256": file_hash(run_dir / "datasets/calibration.json"),
        "max_planned_target_calls": len(arms) * (calibration_n + holdout_n),
        "historical_control": {"full_skill": "outputs/repro_searchqa/full_gpt55_seed42/best_skill.md",
                               "initial_skill": "skillopt/envs/searchqa/skills/initial.md",
                               "audit": "outputs/repro_searchqa/full_gpt55_seed42/audit_metrics.json",
                               "historical_test_already_exposed": True},
        "notes": ["Original SearchQA system/user builders, 6000-character context truncation and evaluator are reused.",
                  "Base is the exact historical initial.md, not a newly invented empty/system prompt.",
                  "Full skill has historical source gains on already exposed tasks; these are not fresh holdout evidence.",
                  "Extractive is a separately evaluated section ablation and does not inherit the full skill's benefit.",
                  "Only calibration is materialized before explicit test phase; holdout IDs/fingerprints are preregistered.",
                  "Oracle answers are passed only to scoring, never to model request construction.",
                  "Calibration screens a fixed arm list; it neither edits skills nor selects a new arm using holdout.",
                  "Shared task-level pairing and common successful IDs do not remove model/API stochasticity.",
                  "Semantic duplicates, pretraining exposure and use outside known local logs cannot be excluded."],
    }
    write_immutable_json(protocol_path, protocol)
    return protocol


class SourceCachedAPI:
    """Real target calls, with an isolated cache and no silent retry of terminal failures."""

    def __init__(self, repo: Path, root: Path, protocol: dict[str, Any]):
        from urllib.parse import urlparse

        from skillopt.cross_domain.runtime import configure_api
        from skillopt.model.openai_compatible_backend import TARGET_CONFIG

        self.provider = configure_api(repo, protocol["model"], protocol["effective_max_tokens_cap"])
        if self.provider["provider_host"] != protocol["required_provider_host"]:
            raise ValueError("Configured provider is not the preregistered Freerouter host")
        parsed = urlparse(TARGET_CONFIG.base_url)
        self.service = {"host": parsed.hostname, "path": parsed.path, "cap": TARGET_CONFIG.max_tokens,
                        "temperature": TARGET_CONFIG.temperature}
        self.root, self.protocol = Path(root), protocol
        write_immutable_json(self.root / "source_provider.json", {"provider": self.provider, "service": self.service})

    def call(self, system: str, user: str, *, key: str, arm: str, split: str) -> dict[str, Any]:
        from skillopt.cross_domain.runtime import safe_error
        from skillopt.model import chat_target

        request = {"protocol": self.protocol["protocol_version"], "model": self.protocol["model"],
                   "system": system, "user": user, "key": key, "arm": arm, "split": split,
                   "service": self.service, "max_completion_tokens": self.protocol["requested_max_completion_tokens"]}
        identifier = digest(request)
        path = self.root / "calls" / (identifier + ".json")
        if path.exists():
            record = read_json(path)
            if record["request_hash"] != identifier or record["request"] != request:
                raise ValueError("Source request cache does not match its frozen request")
            return record
        start = time.monotonic()
        try:
            response, usage = chat_target(system=system, user=user,
                                          max_completion_tokens=request["max_completion_tokens"],
                                          retries=3, timeout=90, stage="source_retention_" + split)
            outcome = {"ok": True, "response": response, "usage": usage}
        except Exception as error:
            outcome = {"ok": False, "response": "", "usage": {}, "error": safe_error(error)}
        record = {"request_hash": identifier, "request": request, **outcome,
                  "wall_seconds": time.monotonic() - start}
        write_immutable_json(path, record)
        return record


def _rollout(api, tasks: list[dict], skill: str, arm: str, split: str, root: Path, workers: int) -> list[dict]:
    path = root / "searchqa_rollouts" / split / arm / "results.jsonl"
    if path.exists():
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        if [row["id"] for row in rows] != [task["id"] for task in tasks]:
            raise ValueError("Saved source rollout IDs/order differ from the manifest")
        for row, task in zip(rows, tasks):
            if (row.get("arm") != arm or row.get("split") != split or row.get("env") != "searchqa"
                    or row.get("skill_sha256") != hashlib.sha256(skill.encode()).hexdigest()
                    or row.get("question_sha256") != question_fingerprint(task["question"])
                    or row.get("question") != task["question"] or row.get("gold_answers") != task["answers"]):
                raise ValueError("Saved source rollout provenance differs from frozen inputs")
            if not isinstance(row.get("agent_ok"), bool) or not isinstance(row.get("request_hash"), str):
                raise ValueError("Invalid saved source API status/provenance")
            if row["agent_ok"]:
                expected = evaluate(row["response"], task["answers"])
                if any(row.get(key) != expected[key] for key in ("em", "f1", "predicted_answer")) or row.get("hard") != expected["em"]:
                    raise ValueError("Saved source scores disagree with the frozen original evaluator")
            elif any(row.get(key) is not None for key in ("hard", "em", "f1")):
                raise ValueError("API errors must not contain scored model outcomes")
        return rows
    system = _build_system(skill)

    def one(task):
        user = _build_user(task["question"], task["context"])
        response = api.call(system, user, key=task["id"], arm=arm, split=split)
        # Gold cannot affect prompt construction or the request hash.
        metric = evaluate(response["response"], task["answers"]) if response["ok"] else {}
        return {"id": task["id"], "question": task["question"], "question_sha256": question_fingerprint(task["question"]),
                "split": split, "arm": arm, "env": "searchqa", "agent_ok": response["ok"],
                "hard": metric.get("em"), "em": metric.get("em"), "f1": metric.get("f1"),
                "predicted_answer": metric.get("predicted_answer"), "gold_answers": task["answers"],
                "response": response["response"], "request_hash": response["request_hash"],
                "skill_sha256": hashlib.sha256(skill.encode()).hexdigest(),
                "api_error": response.get("error"), "usage": response.get("usage", {})}

    print(f"[source {split}/{arm}] {len(tasks)} tasks, workers={workers}", flush=True)
    start = time.monotonic()
    rows = []
    with ThreadPoolExecutor(max_workers=workers) as executor:
        for index, row in enumerate(executor.map(one, tasks), 1):
            rows.append(row)
            if index % 20 == 0 or index == len(tasks):
                print(f"[source {split}/{arm}] {index}/{len(tasks)} elapsed={time.monotonic()-start:.1f}s", flush=True)
    _write_text_snapshot(path, "".join(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n" for row in rows))
    print(f"[source {split}/{arm}] complete, api_errors={sum(not row['agent_ok'] for row in rows)}", flush=True)
    return rows


def summarize(outcomes: dict[str, list[dict]], *, seed: int = 20260908, bootstrap_n: int = 5000) -> dict[str, Any]:
    lookups = {arm: {row["id"]: row for row in rows} for arm, rows in outcomes.items()}
    expected = set(lookups["base"])
    if any(set(rows) != expected or len(rows) != len(outcomes[arm]) for arm, rows in lookups.items()):
        raise ValueError("All source arms must have the same unique task IDs")
    common = sorted(task_id for task_id in expected if all(rows[task_id]["agent_ok"] for rows in lookups.values()))
    n = len(common)
    arms = {}
    for arm, rows in lookups.items():
        successful = [row for row in rows.values() if row["agent_ok"]]
        arms[arm] = {"n_expected": len(expected), "n_api_success": len(successful),
                     "n_api_error": len(expected) - len(successful), "n_common_success": n,
                     "em": sum(rows[i]["em"] for i in common) / n if n else None,
                     "f1": sum(rows[i]["f1"] for i in common) / n if n else None,
                     "correct_common": sum(rows[i]["hard"] for i in common),
                     "em_own_success_diagnostic": sum(row["em"] for row in successful) / len(successful) if successful else None}
    comparisons = {}
    for arm, rows in lookups.items():
        if arm == "base":
            continue
        pairs = [{"id": i, "domain": "searchqa", "mechanism": arm, "group": "source",
                  "baseline": lookups["base"][i]["hard"], "current": lookups["base"][i]["hard"],
                  "candidate": rows[i]["hard"]} for i in common]
        paired = pair_stats(pairs)["comparisons"]["baseline"]
        if n:
            delta = np.array([[rows[i][key] - lookups["base"][i][key] for key in ("em", "f1")] for i in common])
            rng = np.random.default_rng(seed)
            boot = np.array([delta[rng.integers(0, n, n)].mean(axis=0) for _ in range(bootstrap_n)])
            intervals = np.quantile(boot, [.025, .975], axis=0)
            ci = {key: [float(intervals[0, index]), float(intervals[1, index])] for index, key in enumerate(("em", "f1"))}
            deltas = {key: float(delta[:, index].mean()) for index, key in enumerate(("em", "f1"))}
        else:
            ci, deltas = {key: [None, None] for key in ("em", "f1")}, {key: None for key in ("em", "f1")}
        comparisons[arm] = {"n": n, "paired": paired, "delta": deltas, "paired_bootstrap95": ci,
                            "positive_gain_screen": bool(n and deltas["em"] > 0 and ci["em"][0] > 0
                                                          and paired["exact_paired_p"] < .05)}
    return {"arms": arms, "vs_base": comparisons, "common_ids": common,
            "excluded_ids_missing_any_arm": sorted(expected - set(common)),
            "bootstrap": {"unit": "original task", "n_resamples": bootstrap_n, "seed": seed},
            "notes": ["All headline arm and pair scores use the same successful-ID intersection across all arms.",
                      "API failures remain separate, never scored as model errors; complete-case filtering can still be biased.",
                      "Paired task bootstrap and exact zero-gain test describe this fixed skill/model run only.",
                      "Intervals are not adjusted across arms, screenings or repeated experiments; no safety certification."]}


def _report(root: Path, split: str, summary: dict[str, Any]) -> None:
    def pct(value):
        return "N/A" if value is None else f"{100 * value:.2f}%"
    lines = [f"# SearchQA 来源收益复核：{split}", "",
             "固定完整 Skill 与独立 extractive 消融；这不是跨域有效性证明，也不是历史测试集的重用。", "",
             "| Arm | 共同成功题数 | EM | F1 | API 错误 |", "|---|---:|---:|---:|---:|"]
    for arm, value in summary["arms"].items():
        lines.append(f"| {arm} | {value['n_common_success']} | {pct(value['em'])} | {pct(value['f1'])} | {value['n_api_error']} |")
    lines.extend(["", "| 相对 Base | 错→对 | 对→错 | EM 增益 | EM 配对 bootstrap 95% 区间 |", "|---|---:|---:|---:|---|"])
    for arm, value in summary["vs_base"].items():
        pair, ci = value["paired"], value["paired_bootstrap95"]["em"]
        lines.append(f"| {arm} | {pair['wins']} | {pair['losses']} | {pct(value['delta']['em'])} | {pct(ci[0])} 至 {pct(ci[1])} |")
    lines.extend(["", "## 边界", "",
                  "- calibration 仅用于固定三臂的来源筛查；holdout 只在协议、Skill、实现冻结后显式启动。",
                  "- 原完整 Skill 的 +7.79pp 是已暴露旧题的历史证据；extractive 不能继承该收益。",
                  "- 本轮候选均不编辑、不根据 holdout 重选；是否继续 holdout 可根据 calibration 决定。",
                  "- 只排除已知本地运行 ID、过去预留 source ID 和精确归一化问题重复，不能排除语义重复或预训练污染。",
                  "- 所有主指标采用全臂共同 API 成功样本；错误数与排除 ID 单独保存，排除不代表无偏。",
                  "- 区间描述单种子、单次生成及固定样本；未做跨臂、多轮筛查校正，不是正式安全保证。", ""])
    _write_text_snapshot(root / f"{split}_report.md", "\n".join(lines))


def run_phase(repo: Path, run_dir: Path, phase: str, *, arms=DEFAULT_ARMS, workers: int = 6,
              seed: int = 20260908, calibration_n: int = 128, holdout_n: int = 256,
              cache_path: Path = DEFAULT_CACHE, api=None) -> dict[str, Any]:
    """prepare is network-free; pilot/test run only when explicitly requested."""
    if phase not in {"prepare", "pilot", "test"}:
        raise ValueError("phase must be prepare, pilot or test")
    root = Path(run_dir).resolve()
    protocol = prepare(repo, root, arms=arms, workers=workers, seed=seed,
                       calibration_n=calibration_n, holdout_n=holdout_n, cache_path=cache_path)
    if phase == "prepare":
        return {"phase": phase, "protocol_hash": digest(protocol), "manifest_hash": protocol["manifest_hash"],
                "calibration_n": calibration_n, "holdout_n": holdout_n, "arms": list(arms),
                "holdout_payload_materialized": False, "planned_calls": protocol["max_planned_target_calls"]}
    manifest = read_json(root / "source_manifest.json")
    frozen_path = root / "frozen_source_protocol.json"
    execution_mode = "real_target_api" if api is None else "injected_test_double"
    if phase == "test":
        if not frozen_path.exists():
            raise ValueError("Complete calibration and freeze source protocol before opening holdout")
        frozen = read_json(frozen_path)
        if frozen["protocol_hash"] != digest(protocol) or frozen["code_hashes"] != _code_hashes():
            raise ValueError("Frozen source protocol or code changed before holdout")
        if frozen["execution_mode"] != execution_mode:
            raise ValueError("Cannot mix mock and real API calibration/holdout evidence")
        for relative, expected in frozen["calibration_artifact_hashes"].items():
            if file_hash(root / relative) != expected:
                raise ValueError("Calibration evidence changed after source freeze")
        tasks = materialize_source_split(manifest, "holdout")
        write_immutable_json(root / "datasets/holdout.json", tasks)
        split = "holdout"
    else:
        tasks = read_json(root / "datasets/calibration.json")
        split = "calibration"
    client = api if api is not None else SourceCachedAPI(Path(repo), root, protocol)
    outcomes = {arm: _rollout(client, tasks, (root / protocol["arms"][arm]["snapshot"]).read_text(encoding="utf-8"),
                               arm, split, root, workers) for arm in arms}
    usage_keys = ("prompt_tokens", "completion_tokens", "total_tokens")
    summary = {"phase": phase, "split": split, "protocol_hash": digest(protocol), "execution_mode": execution_mode,
               "usage": {key: sum(row.get("usage", {}).get(key, 0) for rows in outcomes.values() for row in rows) for key in usage_keys},
               "n_logical_target_calls": sum(len(rows) for rows in outcomes.values()),
               **summarize(outcomes, seed=seed)}
    write_immutable_json(root / f"{split}_summary.json", summary)
    _report(root, split, summary)
    if phase == "pilot":
        paths = ["calibration_summary.json", "datasets/calibration.json"] + [f"searchqa_rollouts/calibration/{arm}/results.jsonl" for arm in arms]
        if (root / "source_provider.json").exists():
            paths.append("source_provider.json")
        write_immutable_json(frozen_path, {"protocol_hash": digest(protocol), "code_hashes": _code_hashes(),
                                         "manifest_hash": digest(manifest), "holdout_accessed": False,
                                         "execution_mode": execution_mode,
                                         "arms": protocol["arms"],
                                         "calibration_artifact_hashes": {path: file_hash(root / path) for path in paths},
                                         "notes": ["No held-out task payload or outcome was used to freeze this protocol.",
                                                   "All original fixed arms remain; extractive has independent attribution."]})
    return summary
