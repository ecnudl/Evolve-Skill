"""Input-only routing and validation-fitted scope proposals.

Generator annotations are only used for evaluation strata, NEVER for routing.
Fit and confirmation partitions are disjoint. Only the latter enters the gate.
"""
from __future__ import annotations

import json
import math
import random
from collections import defaultdict

from skillopt.cross_domain.runtime import CachedAPI, digest, write_json


def propose_mechanism_scopes(api: CachedAPI, skills: list[dict]) -> list[dict]:
    """Propose broader prerequisites without changing content or claiming evidence.

    Domain-specific syntax is not a prerequisite unless the procedure really
    depends on it. These proposals are later tested, never self-certified.
    """
    from skillopt.utils import extract_json
    proposed = []
    for skill in skills:
        call = api.call(
            "Infer the underlying problem-solving mechanism of a local procedural skill. "
            "Propose testable applicability conditions from observable task features, not domain names. "
            "Distinguish essential preconditions from incidental example syntax or output format. "
            "If the actual procedure is domain-specific do not falsely make it universal. "
            "Return JSON with apply_if (list), avoid_if (list), description (string). "
            "This is an unvalidated scope hypothesis; do not edit the skill, claim success, or see any evaluation outcomes.",
            skill["content"], kind="mechanism_scope", key=skill["id"], max_tokens=1800)
        obj = extract_json(call["response"]) if call["ok"] else None
        if not isinstance(obj, dict) or not isinstance(obj.get("apply_if"), list) or not isinstance(obj.get("avoid_if"), list):
            raise ValueError("Invalid mechanism-scope hypothesis")
        proposed.append({**skill, "local_scope": skill["scope"], "scope": obj,
                         "scope_status": "unvalidated hypothesis", "scope_request_hash": call["request_hash"]})
    write_json(api.root / "scope_hypotheses_before_validation.json", proposed)
    return proposed


def route_inputs(api: CachedAPI, tasks: list, skills: list[dict], label: str) -> dict:
    from skillopt.utils import extract_json
    descriptions = [{"id": s["id"], "description": s["scope"].get("description", ""),
                     "apply_if": s["scope"].get("apply_if", []), "avoid_if": s["scope"].get("avoid_if", [])}
                    for s in skills]
    system = (
        "You are a conservative procedural-skill applicability router, not a task solver. "
        "Inspect only the task input and proposed prerequisites. Decide whether each skill is "
        "appropriate BEFORE solving. Explicit task instructions override a reusable skill. "
        "If the prerequisites are contradicted or irrelevant give a low score; uncertainty is not permission. "
        "Return JSON with domain (coding/spreadsheet/rule_reasoning/unknown) and scores "
        "(object mapping EVERY skill id to a number from 0 to 1). Do not answer the task.\n"
        + json.dumps(descriptions, ensure_ascii=False)
    )
    def one(task):
        record = api.call(system, task.prompt, kind="router", key=task.id, max_tokens=1200)
        try:
            result = extract_json(record["response"]) if record["ok"] else None
            if not isinstance(result, dict) or result.get("domain") not in {"coding", "spreadsheet", "rule_reasoning", "unknown"}:
                raise ValueError("Invalid domain")
            scores = {s["id"]: float(result["scores"][s["id"]]) for s in skills}
            if not all(math.isfinite(v) and 0 <= v <= 1 for v in scores.values()):
                raise ValueError("Invalid score")
            return task.id, {"ok": True, "domain": result["domain"], "scores": scores,
                             "request_hash": record["request_hash"]}
        except (TypeError, ValueError, KeyError):
            return task.id, {"ok": False, "domain": "unknown", "scores": {s["id"]: 0.0 for s in skills},
                             "request_hash": record["request_hash"]}
    results = dict(api.parallel(tasks, one, label))
    write_json(api.root / "routes" / (label + ".json"), results)
    return results


def partition_validation(tasks: list) -> tuple[list, list]:
    cells = defaultdict(list)
    for t in tasks:
        cells[t.domain, t.mechanism, t.group].append(t)
    fit, confirm = [], []
    for key in sorted(cells):
        ordered = sorted(cells[key], key=lambda t: t.id)
        fit.extend(ordered[::2])
        confirm.extend(ordered[1::2])
    return fit, confirm


def route_labels(tasks: list, routes: dict, skill_id: str, threshold: float, seed: int) -> dict:
    labels = {"mechanism": {}, "domain": {}, "shuffled": {}}
    # Permute input-only applicability labels, preserving EXACT match coverage
    # within predicted-domain buckets. Neither gold nor experimental mechanism
    # labels nor outcomes enter the permutation.
    buckets = defaultdict(list)
    for task in tasks:
        r = routes[task.id]
        if not r["ok"]:
            for method in labels:
                labels[method][task.id] = "__abstain__"
            continue
        match = "match" if r["ok"] and r["scores"][skill_id] >= threshold else "nonmatch"
        labels["mechanism"][task.id] = match
        labels["domain"][task.id] = r["domain"]
        buckets[r["domain"]].append(task.id)
    for domain, ids in sorted(buckets.items()):
        ids.sort()
        values = [labels["mechanism"][tid] for tid in ids]
        rng = random.Random(digest([seed, skill_id, domain, ids]))
        rng.shuffle(values)
        labels["shuffled"].update(zip(ids, values))
    return labels


def paired_rows(tasks, baseline, current, candidate, *, mask=None, mechanism=None, parent_empty=False):
    lookup = [{r["id"]: r for r in rows} for rows in (baseline, current, candidate)]
    result = []
    for task in tasks:
        b, c, s = [items[task.id] for items in lookup]
        applied = True if mask is None else bool(mask[task.id])
        outcome = s if applied else b
        if not all(r["agent_ok"] for r in (b, c, outcome)):
            continue
        group = task.group
        if group == "positive" and mechanism is not None and task.mechanism != mechanism:
            group = "unrelated"
        result.append({"id": task.id, "domain": task.domain, "mechanism": task.mechanism,
                       "group": group, "original_group": task.group,
                       "baseline": b["hard"], "current": c["hard"], "candidate": outcome["hard"],
                       "applied": applied, "candidate_is_baseline": not applied,
                       "current_is_baseline": parent_empty})
    return result


def fit_scope_groups(tasks, labels, baseline, current, candidate, parent_empty=False) -> dict:
    """Identical point-estimate proposal rule for all grouping ablations.

    This is learning, not certification. An independent confirmation split must
    pass the full per-cell gate. Unseen group labels always fall back.
    """
    from skillopt.cross_domain.gate import pair_stats
    rows = paired_rows(tasks, baseline, current, candidate, parent_empty=parent_empty)
    result = {}
    for method, mapping in labels.items():
        groups = defaultdict(list)
        for row in rows:
            groups[mapping[row["id"]]].append(row)
        estimates = {key: pair_stats(value) for key, value in groups.items()}
        allowed = [key for key, stats in estimates.items()
                   if key not in {"__abstain__", "unknown"} and stats["n"] >= 16
                   and all(stats["comparisons"][ref]["delta"] > 0 for ref in ("baseline", "current"))]
        result[method] = {"allowed_groups": sorted(allowed), "estimates": estimates,
                          "proposal_rule": "n>=16 and positive empirical gain vs both references; independent confirmation required"}
    return result


def mask_from_scope(labels: dict, allowed: list) -> dict:
    return {tid: label not in {"__abstain__", "unknown"} and label in allowed for tid, label in labels.items()}


def matched_coverage_masks(tasks, routes, skill, fraction: float, seed: int) -> dict:
    """Predeclared input-only ranking diagnostic; no gating or gold used.

    Exactly equal number and length of injected skills across three methods.
    Domain ranks source-domain tasks first; hashes break ties. Shuffled permutes
    the applicability scores. Diagnostic masks are NOT permission to deploy.
    """
    n = round(len(tasks) * fraction)
    ids = sorted(t.id for t in tasks)
    def tie(tid):
        return digest([seed, skill["id"], tid])
    scores = {tid: routes[tid]["scores"][skill["id"]] for tid in ids}
    values = list(scores.values())
    random.Random(digest([seed, skill["id"], ids, "coverage"])).shuffle(values)
    shuffled = dict(zip(ids, values))
    rankings = {
        "mechanism": sorted(ids, key=lambda tid: (-scores[tid], tie(tid))),
        "domain": sorted(ids, key=lambda tid: (routes[tid]["domain"] != skill["source_domain"], tie(tid))),
        "shuffled": sorted(ids, key=lambda tid: (-shuffled[tid], tie(tid))),
    }
    result = {}
    for name, order in rankings.items():
        selected = set(order[:n])
        result[name] = {tid: tid in selected for tid in ids}
    return result
