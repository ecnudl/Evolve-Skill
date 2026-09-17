"""Artifact-task successor to the frozen first pilot, using explicit adapters.

No v1 source/artifacts are edited. The process-local adapter reuses its candidate
engine, routing, split confirmation gate and offline-policy statistics, replacing
only task generation/evaluation and the code-hash boundary. Never run this adapter
concurrently with another experiment in the SAME Python process.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from contextlib import contextmanager
from pathlib import Path

from skillopt.cross_domain import evolution
from skillopt.cross_domain import experiment as core
from skillopt.cross_domain.runtime import TARGET_SYSTEM, CachedAPI, configure_api, digest, read_json, write_json


def code_hashes(repo):
    paths = list((repo / "skillopt/cross_domain").glob("*.py"))
    paths += [repo / "skillopt/scope_evolution_v2" / name for name in (
        "__init__.py", "tasks.py", "experiment.py")]
    paths += [repo / "scripts/artifact_scope_mvp.py"]
    return {str(path.relative_to(repo)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(paths) if path.is_file()}


def artifact_dataset(root, protocol, split):
    from skillopt.scope_evolution_v2.tasks import build_tasks
    domains = ["coding"] if split in {"train", "dev"} else (
        ["coding", "spreadsheet"] if split == "validation" else
        ["coding", "spreadsheet", "rule_reasoning"])
    tasks = build_tasks(seed=protocol["seed"], split=split,
                        n_per_cell=protocol[f"{split}_per_cell"], domains=domains,
                        mechanisms=protocol["mechanisms"], difficulty=protocol["difficulty"])
    values = [task.to_dict() for task in tasks]
    path = root / "datasets" / f"{split}.json"
    if path.exists() and digest(read_json(path)) != digest(values):
        raise ValueError("Artifact dataset changed; keep this run and use a new output directory")
    write_json(path, values)
    return tasks


def artifact_rollout(api, tasks, skill, label, repeat=0):
    from skillopt.scope_evolution_v2.tasks import evaluate_answer
    system = TARGET_SYSTEM + ("\n\nReusable procedural guidance:\n" + skill if skill else "")

    def one(task):
        call = api.call(system, task.prompt, kind="target", key=task.id,
                        max_tokens=4000, repeat=repeat)
        evaluation = evaluate_answer(task, call["response"])
        return {"id": task.id, "domain": task.domain, "mechanism": task.mechanism,
                "group": task.group, "family": task.family, "split": task.split,
                "hard": int(evaluation["correct"]) if call["ok"] else None,
                "agent_ok": call["ok"], "evaluation": evaluation,
                "response": call["response"], "request_hash": call["request_hash"],
                "skill_hash": digest(skill), "repeat": repeat, "usage": call["usage"]}

    rows = api.parallel(tasks, one, label)
    write_json(api.root / "rollouts" / f"{label}.json", rows)
    valid = [row for row in rows if row["agent_ok"]]
    print(f"[{label}] EM={sum(row['hard'] for row in valid)}/{len(valid)}, "
          f"api_errors={len(rows)-len(valid)}", flush=True)
    return rows


@contextmanager
def artifact_adapter(protocol):
    """Restore module globals even on failure; disk source remains unchanged."""
    mechanisms = protocol["mechanisms"]
    if (not isinstance(mechanisms, (list, tuple)) or not mechanisms
            or any(name not in {"constraint_preservation", "evidence_verification"} for name in mechanisms)):
        raise ValueError("Provide a nonempty sequence of supported mechanisms")
    from skillopt.gradient import aggregate, reflect
    from skillopt.optimizer import clip
    bindings = [(core, "dataset", artifact_dataset), (core, "rollout", artifact_rollout),
                (core, "_code_hashes", code_hashes), (evolution, "rollout", artifact_rollout),
                (evolution, "MECHANISMS", tuple(mechanisms))]
    old = [(module, name, getattr(module, name)) for module, name, _ in bindings]
    old += [(module, "chat_optimizer", module.chat_optimizer) for module in (aggregate, reflect, clip)]
    try:
        for module, name, value in bindings:
            setattr(module, name, value)
        yield
    finally:
        for module, name, value in old:
            setattr(module, name, value)


def learnability_screen(root, protocol):
    """A train/dev-only futility screen, never a scope certificate.

    A source with no observed mistakes cannot identify positive improvement.
    Very low accuracy calls for task/API debugging before expensive evolution.
    These bounds and the single-screen sample size are fixed in the protocol.
    """
    outcomes = {}
    usable = []
    for mechanism in protocol["mechanisms"]:
        cells = {}
        for split in ("train", "dev"):
            rows = [row for row in read_json(root / "rollouts" / f"pilot_{split}.json")
                    if row["mechanism"] == mechanism and row["group"] == "positive"]
            if (len(rows) != protocol[f"{split}_per_cell"]
                    or len({row.get("id") for row in rows}) != len(rows)
                    or not all(isinstance(row.get("id"), str) and row["id"]
                               and row.get("agent_ok") is True and type(row.get("hard")) is int
                               and row["hard"] in (0, 1) for row in rows)):
                raise ValueError("Incomplete or invalid source screen; API failures are not task difficulty")
            cells[split] = {"n": len(rows), "correct": sum(row["hard"] for row in rows),
                            "em": sum(row["hard"] for row in rows) / len(rows)}
        low, high = protocol["source_screen_range"]
        passed = all(low <= cell["em"] <= high for cell in cells.values())
        outcomes[mechanism] = {"cells": cells, "worth_evolving": passed}
        if passed:
            usable.append(mechanism)
    result = {"mechanisms": outcomes, "all_tracks_pass": len(usable) == len(protocol["mechanisms"]),
              "rule": "Both train and dev positive baseline EM within fixed source_screen_range",
              "not_a_benefit_or_safety_certificate": True, "test_accessed": False}
    write_json(root / "learnability_screen.json", result)
    return result


def prepare(repo, root, protocol, provider):
    manifest = {"protocol": protocol, "provider": provider,
                "generator_sha256": hashlib.sha256((repo / "skillopt/scope_evolution_v2/tasks.py").read_bytes()).hexdigest(),
                "artifact_evaluator": "trusted bounded interpreter; never execute arbitrary model code",
                "historical_test_exclusion": "v1 is development evidence only; v2 uses separate new tasks and its test is not accessed for tuning"}
    path = root / "protocol.json"
    if path.exists() and read_json(path) != manifest:
        raise ValueError("Changed protocol/provider/generator: use a new artifact run directory")
    write_json(path, manifest)


def source_update_screen(root):
    candidates = read_json(root / "candidates.json")
    def valid_score(value):
        return type(value) in (int, float) and math.isfinite(value) and 0 <= value <= 1
    evidence = [{"id": skill["id"], "dev_em": skill["dev_em"],
                 "previous_dev_em": skill["previous_dev_em"],
                 "point_gate_accepted": skill["accepted_local_point_gate"] is True,
                 "nonempty_content": isinstance(skill.get("content"), str) and bool(skill["content"].strip())}
                for skill in candidates["selected"]]
    for row in evidence:
        row["invalid_score_fields"] = [field for field in ("dev_em", "previous_dev_em") if not valid_score(row[field])]
        for field in row["invalid_score_fields"]:
            row[field] = None
    result = {"all_tracks_show_source_gain": bool(evidence)
        and len({row["id"] for row in evidence}) == len(evidence) and all(
        row["nonempty_content"] and row["point_gate_accepted"] and valid_score(row["dev_em"])
        and valid_score(row["previous_dev_em"]) and row["dev_em"] > row["previous_dev_em"] for row in evidence),
        "selected": evidence, "not_a_statistical_scope_certificate": True,
        "rule": "Require nonempty dev-selected candidates to pass the source point gate before full cross-domain validation"}
    write_json(root / "source_update_screen.json", result)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="configs/cross_domain/artifact_v2.json")
    parser.add_argument("--out", default="outputs/cross_domain/artifact_v2_hard_seed20260908")
    parser.add_argument("--phase", choices=("pilot", "train", "validate", "test", "all"), default="all")
    args = parser.parse_args(argv)
    repo = Path(__file__).resolve().parents[2]
    protocol = read_json(repo / args.config)
    root = (repo / args.out).resolve()
    if root == repo or repo not in root.parents:
        raise ValueError("Use a dedicated artifact output directory inside the repository")
    provider = configure_api(repo, protocol["model"])
    prepare(repo, root, protocol, provider)
    api = CachedAPI(root, protocol["model"], protocol["workers"])
    with artifact_adapter(protocol):
        if args.phase in {"pilot", "all"}:
            core.pilot(api, protocol)
            screen = learnability_screen(root, protocol)
            print(json.dumps(screen, ensure_ascii=False), flush=True)
            if args.phase == "all" and not screen["all_tracks_pass"]:
                print("[futility] No identifiable source headroom for every track; do not access validation/test.", flush=True)
                return
        if args.phase in {"train", "all"}:
            screen = read_json(root / "learnability_screen.json")
            if not screen["all_tracks_pass"]:
                raise ValueError("Source screen failed; change source-only task design in a NEW run")
            evolution.generate_candidates(api, artifact_dataset(root, protocol, "train"),
                                          artifact_dataset(root, protocol, "dev"), protocol)
            if not source_update_screen(root)["all_tracks_show_source_gain"]:
                print("[futility] No source dev improvement; retain the run without accessing validation/test.", flush=True)
                return
        if args.phase in {"validate", "all"}:
            if not source_update_screen(root)["all_tracks_show_source_gain"]:
                raise ValueError("No source gain: do not perform expensive scope validation")
            core.validate(api, protocol, repo)
        if args.phase in {"test", "all"}:
            core.test(api, protocol, repo)
    print(f"[complete] artifact phase={args.phase} output={root}", flush=True)


if __name__ == "__main__":
    main()
