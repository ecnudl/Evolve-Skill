"""Reuse SkillOpt's real minibatch reflection, merge, ranking and patch engine."""
from __future__ import annotations

import json

from skillopt.cross_domain.runtime import CachedAPI, digest, read_json, rollout, write_json

MECHANISMS = ("constraint_preservation", "evidence_verification")


def select_candidate(candidates: list[dict]) -> dict:
    """A no-op is the baseline, not a candidate intervention to compare."""
    nonempty = [r for r in candidates if r["content"].strip()]
    if not nonempty:
        raise RuntimeError("No nonempty candidate; cannot run a skill intervention")
    return sorted(nonempty, key=lambda r: (-r["dev_em"], len(r["content"]), r["id"]))[0]


def _install_cached_optimizer(api: CachedAPI):
    from skillopt.gradient import aggregate, reflect
    from skillopt.optimizer import clip
    def invoke(system, user, max_completion_tokens=8000, stage="optimizer", **kwargs):
        record = api.call(system, user, kind="optimizer", key=stage,
                          max_tokens=min(max_completion_tokens, 8000))
        if not record["ok"]:
            raise RuntimeError(record.get("error", "Optimizer unavailable"))
        return record["response"], record["usage"]
    # Process-local transport injection, preserving the upstream algorithm/prompts.
    for module in (reflect, aggregate, clip):
        module.chat_optimizer = invoke


def generate_candidates(api: CachedAPI, train: list, dev: list, protocol: dict) -> dict:
    from skillopt.gradient.aggregate import merge_patches
    from skillopt.gradient.reflect import run_error_analyst_minibatch, run_success_analyst_minibatch
    from skillopt.optimizer.clip import rank_and_select
    from skillopt.optimizer.skill import apply_patch_with_report
    from skillopt.utils import extract_json
    if any(t.domain != "coding" or t.split != "train" for t in train):
        raise ValueError("Candidate generation accepts coding train only")
    if any(t.domain != "coding" or t.split != "dev" for t in dev):
        raise ValueError("Candidate selection accepts coding dev only")
    output = api.root / "candidates.json"
    if output.exists():
        return read_json(output)
    _install_cached_optimizer(api)
    pool, histories, selected = [], [], []
    for mechanism in MECHANISMS:
        source_train = [t for t in train if t.mechanism == mechanism and t.group == "positive"]
        source_dev = [t for t in dev if t.mechanism == mechanism and t.group == "positive"]
        current, current_id = "", "base"
        base_dev = rollout(api, source_dev, "", f"dev_{mechanism}_base")
        if not all(r["agent_ok"] for r in base_dev):
            raise RuntimeError("API failure in selection data; abort rather than select on failures")
        current_score = sum(r["hard"] for r in base_dev) / len(base_dev)
        candidates_for_track = []
        rejected = []
        for round_i in range(protocol["candidate_rounds"]):
            candidate_id = f"{mechanism}_v{round_i+1}"
            checkpoint = api.root / "evolution" / f"{candidate_id}.json"
            if checkpoint.exists():
                info = read_json(checkpoint)
            else:
                rows = rollout(api, source_train, current, "train_" + candidate_id)
                if not all(r["agent_ok"] for r in rows):
                    raise RuntimeError("API failure in training rollout; abort before reflection")
                predictions = api.root / "evolution" / candidate_id / "predictions"
                items = []
                for task, row in zip(source_train, rows):
                    write_json(predictions / task.id / "conversation.json", [
                        {"role": "user", "content": task.prompt},
                        {"role": "assistant", "content": row["response"]},
                        {"role": "system", "content": f"Hard oracle score: {row['hard']}; expected JSON answer: {json.dumps(task.gold)}"}
                    ])
                    items.append({"id": task.id, "hard": row["hard"], "task_description": task.prompt,
                                  "task_type": mechanism, "n_turns": 1,
                                  "fail_reason": "" if row["hard"] else row["evaluation"]["reason"]})
                failure, success = [], []
                for hard, fn, dest in ((0, run_error_analyst_minibatch, failure),
                                        (1, run_success_analyst_minibatch, success)):
                    subset = [r for r in items if r["hard"] == hard]
                    for start in range(0, len(subset), 8):
                        result = fn(current,
                                    subset[start:start+8], str(predictions),
                                    edit_budget=protocol["edit_budgets"][round_i],
                                    step_buffer_context=json.dumps(rejected))
                        if result:
                            dest.append(result.get("patch", result))
                merged = merge_patches(current, failure, success, batch_size=8, workers=2)
                ranked = rank_and_select(current, merged, protocol["edit_budgets"][round_i])
                content, patch_report = apply_patch_with_report(current, ranked)
                failed_optimizer = [read_json(p) for p in (api.root / "calls").glob("*.json")]
                if any(not r["ok"] and r["request"]["kind"] == "optimizer" for r in failed_optimizer):
                    raise RuntimeError("An upstream reflection/merge/ranking call failed; do not treat transport failure as skill evidence")
                if not content.strip():
                    # Record a genuine no-op, never invent a successful skill by hand.
                    content = current
                scope_response = api.call(
                    "Describe the usage boundary of a learned procedural skill. Return JSON with "
                    "keys apply_if (list of observable prerequisites), avoid_if (list), description (string). "
                    "Do not change the skill or claim validated generality. Do not list benchmark IDs.",
                    "Skill:\n" + content, kind="scope", key=candidate_id, max_tokens=1800)
                if not scope_response["ok"]:
                    raise RuntimeError("Scope generation failed")
                scope = extract_json(scope_response["response"])
                if not isinstance(scope, dict) or not isinstance(scope.get("apply_if"), list):
                    raise ValueError("Invalid scope proposal")
                dev_rows = rollout(api, source_dev, content, "dev_" + candidate_id)
                if not all(r["agent_ok"] for r in dev_rows):
                    raise RuntimeError("API failure in dev; cannot select candidate")
                score = sum(r["hard"] for r in dev_rows) / len(dev_rows)
                accepted = bool(content.strip()) and score > current_score
                info = {"id": candidate_id, "mechanism": mechanism, "source_domain": "coding",
                        "content": content, "scope": scope, "content_hash": digest(content),
                        "parent_id": current_id, "parent_content": current,
                        "dev_em": score, "previous_dev_em": current_score,
                        "accepted_local_point_gate": accepted, "patch": ranked,
                        "patch_report": patch_report, "source_train_ids": [t.id for t in source_train],
                        "source_dev_ids": [t.id for t in source_dev]}
                write_json(checkpoint, info)
            pool.append(info)
            candidates_for_track.append(info)
            histories.append({k: v for k,v in info.items() if k not in {"content", "parent_content", "scope"}})
            if info["accepted_local_point_gate"]:
                current, current_id, current_score = info["content"], info["id"], info["dev_em"]
            else:
                rejected.append({"id": info["id"], "score": info["dev_em"], "patch": info["patch"]})
        # Dev-only selection, including when no candidate improves. Keeping a rejected
        # candidate permits an honest forced-injection diagnostic, NOT deployment.
        winner = select_candidate(candidates_for_track)
        selected.append(winner)
    result = {"pool": pool, "selected": selected, "history": histories,
              "selection_rule": "nonempty candidates only; highest coding-dev EM, shorter text, lexicographic id; no validation or test access"}
    write_json(output, result)
    return result
