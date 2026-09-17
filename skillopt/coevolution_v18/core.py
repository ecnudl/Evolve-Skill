"""Pure V18 Skill composition, closed-grid analysis and empirical admission.

This module never calls a model or benchmark. Its caller must authenticate the
receipts and freeze manifests; schema checks do not authenticate evidence.
Question/task-cluster intervals are conditional on the observed learning
histories. Empirical admission is NOT a statistical non-inferiority guarantee.
"""

from __future__ import annotations

import hashlib
import json
import random
from collections import Counter, defaultdict
from statistics import mean

VERSION = "v18-parent-preserving-layered-skill-core-v1"
DOMAINS = ("coding", "searchqa")
ARMS = ("no_skill", "parent", "whole", "core_only", "layered")
BOOTSTRAP_SEED = 2026091801
BOOTSTRAP_SAMPLES = 1000
MAX_PARENT_CHARS = MAX_WHOLE_CHARS = 6000
MAX_CORE_CHARS = 1400
MAX_CODING_PATCH_CHARS = 2800


def _text(value):
    return type(value) is str and bool(value.strip())


def _hash(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _parent(parent):
    if type(parent) is not str or len(parent) > MAX_PARENT_CHARS or "\x00" in parent:
        raise ValueError("Parent must be a string of at most 6000 characters, without NUL")
    return parent


def _markdown(value, maximum):
    # This is a bounded delivery contract, not semantic validation of prose.
    return _text(value) and len(value) <= maximum and "\x00" not in value


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result


def _nonfinite(_):
    raise ValueError("Nonfinite JSON is unsupported")


def parse_update(receipt, parent, mode):
    """Parse one attempt; any invalid delivery aliases the exact parent.

    receipt is the API's {ok: bool, response: str, ...} record. whole requires
    exactly {skill: nonempty Markdown <=6000 chars}; layered requires exactly
    {core: Markdown <=1400, coding_patch: Markdown <=2800}. No retries, JSON
    repair, truncation, hidden assessment or model-judged acceptance occurs.
    Markdown is only checked as bounded nonempty text, not for truth or quality.
    A valid layered record has skill='', because compilation is domain-specific.
    """
    parent = _parent(parent)
    if mode not in {"whole", "layered"}:
        raise ValueError("Mode must be whole or layered")
    base = {"version": VERSION, "mode": mode, "valid": False,
            "reason": "api_unknown", "skill": parent, "core": "", "coding_patch": "",
            "parent_hash": _hash(parent), "invalid_alias": True}
    if type(receipt) is not dict or receipt.get("ok") is not True:
        return base
    raw = receipt.get("response")
    if type(raw) is not str or len(raw) > 60000:
        return {**base, "reason": "response_not_bounded_text"}
    try:
        value = json.loads(raw, object_pairs_hook=_unique_object, parse_constant=_nonfinite)
    except (ValueError, TypeError, RecursionError):
        return {**base, "reason": "invalid_json"}
    expected = {"skill"} if mode == "whole" else {"core", "coding_patch"}
    if type(value) is not dict or set(value) != expected:
        return {**base, "reason": "invalid_schema"}
    limits = {"skill": MAX_WHOLE_CHARS} if mode == "whole" else {
        "core": MAX_CORE_CHARS, "coding_patch": MAX_CODING_PATCH_CHARS}
    for key, limit in limits.items():
        if not _markdown(value[key], limit):
            return {**base, "reason": key + "_contract_invalid"}
    return {**base, "valid": True, "reason": mode + "_candidate", "invalid_alias": False,
            "skill": value["skill"] if mode == "whole" else "",
            "core": value.get("core", ""), "coding_patch": value.get("coding_patch", "")}


def _parsed(parsed, parent):
    parent = _parent(parent)
    if (type(parsed) is not dict or parsed.get("version") != VERSION
            or parsed.get("mode") not in {"whole", "layered"}
            or type(parsed.get("valid")) is not bool or parsed.get("parent_hash") != _hash(parent)
            or parsed.get("invalid_alias") is not (not parsed["valid"])):
        raise ValueError("Parsed update is not bound to the supplied parent")
    if not parsed["valid"]:
        if (parsed.get("skill") != parent or parsed.get("core") != ""
                or parsed.get("coding_patch") != ""):
            raise ValueError("Invalid updates must alias the exact unmodified parent")
    elif parsed["mode"] == "whole":
        if not _markdown(parsed.get("skill"), MAX_WHOLE_CHARS):
            raise ValueError("Whole candidate violates the bounded delivery contract")
    elif (not _markdown(parsed.get("core"), MAX_CORE_CHARS)
          or not _markdown(parsed.get("coding_patch"), MAX_CODING_PATCH_CHARS)):
        raise ValueError("Layered candidate violates the bounded delivery contract")


def compile_core(parsed, parent):
    """Shared-core-only ablation; an invalid update explicitly aliases parent."""
    _parsed(parsed, parent)
    if parsed["mode"] != "layered":
        raise ValueError("core_only requires a layered update")
    return parsed["core"] if parsed["valid"] else parent


def compile_skills(parsed, parent, domain):
    """Compile by trusted domain entry only, never by a hidden task category.

    whole -> same new Skill on both domains.
    layered/coding -> core + new Coding patch.
    layered/searchqa -> core + original parent, retained byte-for-byte as the
    source adapter. Retaining its text does NOT prove behavior preservation:
    the added core can interact with it, hence independent confirmation.
    Source composition may exceed 6000 chars; nothing is silently truncated.
    """
    _parsed(parsed, parent)
    if domain not in DOMAINS:
        raise ValueError("Only the trusted coding/searchqa entry domains are supported")
    if not parsed["valid"]:
        return parent
    if parsed["mode"] == "whole":
        return parsed["skill"]
    heading, adapter = (("Coding procedure", parsed["coding_patch"]) if domain == "coding" else
                        ("SearchQA procedure (retained parent)", parent))
    return "# Shared procedural core\n" + parsed["core"] + "\n\n# " + heading + "\n" + adapter


def _identifiers(values, label):
    if type(values) not in (list, tuple) or not values:
        raise ValueError(label + " manifest must contain unique identifiers")
    try:
        distinct = set(values)
    except TypeError as error:
        raise ValueError(label + " manifest identifiers must be hashable") from error
    if len(values) != len(distinct):
        raise ValueError(label + " manifest must contain unique identifiers")
    return distinct


def _grid(rows, phase, *, expected_tasks=None, expected_arms=None, expected_histories=None):
    if type(rows) is not list or not rows:
        raise ValueError("A nonempty list of materialized observations is required")
    allowed_arms = set(ARMS) if expected_arms is None else _identifiers(expected_arms, "Arm")
    if any(not _text(arm) for arm in allowed_arms):
        raise ValueError("Declared analysis arms must be nonempty strings")
    indexed, metadata, requests = {}, {}, {}
    for row in rows:
        if (type(row) is not dict or row.get("phase") != phase
                or not all(_text(row.get(key)) for key in ("task_id", "cluster_id", "arm", "category", "request_hash"))
                or row.get("domain") not in DOMAINS or row["arm"] not in allowed_arms
                or type(row.get("history")) is not int or row["history"] < 0
                or "hard" not in row
                or not (row["hard"] is None or type(row["hard"]) is int and row["hard"] in (0, 1))):
            raise ValueError("Invalid phase/task/cluster/history/arm or typed outcome schema")
        identity = {key: row[key] for key in ("domain", "cluster_id")}
        if metadata.setdefault(row["task_id"], identity) != identity:
            raise ValueError("Task identity changes across arms or histories")
        evidence = {key: row[key] for key in ("task_id", "domain", "hard", "category")}
        if requests.setdefault(row["request_hash"], evidence) != evidence:
            raise ValueError("One cached request has conflicting task identities or outcomes")
        key = row["task_id"], row["history"], row["arm"]
        if key in indexed:
            raise ValueError("Duplicate task/history/arm observation")
        indexed[key] = row
    tasks = set(metadata)
    histories = {key[1] for key in indexed}
    arms = {key[2] for key in indexed}
    if expected_tasks is not None and tasks != _identifiers(expected_tasks, "Task"):
        raise ValueError("Observed tasks differ from the frozen task manifest")
    if expected_arms is not None and arms != _identifiers(expected_arms, "Arm"):
        raise ValueError("Observed arms differ from the frozen arm manifest")
    if expected_histories is not None and histories != _identifiers(expected_histories, "History"):
        raise ValueError("Observed histories differ from the frozen history manifest")
    if set(indexed) != {(task, history, arm) for task in tasks for history in histories for arm in arms}:
        raise ValueError("Incomplete task x history x arm grid; keep explicit unknown attempts")
    if {info["domain"] for info in metadata.values()} != set(DOMAINS):
        raise ValueError("Both declared domains are required")
    return indexed, metadata, sorted(histories), sorted(arms), len(requests)


def _counts(rows):
    successes = sum(row["hard"] == 1 for row in rows)
    return {"attempts": len(rows), "successes": successes,
            "all_attempt_success_rate": successes / len(rows),
            "unknown": sum(row["hard"] is None for row in rows),
            "categories": dict(sorted(Counter(row["category"] for row in rows).items()))}


def _paired(rows, indexed, arm, reference):
    wins = losses = ties = unknown = alias_pairs = anchor_successes = 0
    for row in rows:
        if row["arm"] != arm:
            continue
        anchor = indexed[row["task_id"], row["history"], reference]
        left, right = int(row["hard"] == 1), int(anchor["hard"] == 1)
        wins += left > right
        losses += left < right
        ties += left == right
        unknown += row["hard"] is None or anchor["hard"] is None
        alias_pairs += row["request_hash"] == anchor["request_hash"]
        anchor_successes += right
    total = wins + losses + ties
    return {"wins": wins, "losses": losses, "ties": ties, "total": total,
            "unknown_pairs": unknown, "same_request_alias_pairs": alias_pairs,
            "delta": (wins - losses) / total if total else None,
            "loss_rate": losses / total if total else None,
            "anchor_successes": anchor_successes,
            "loss_rate_given_anchor_success": losses / anchor_successes if anchor_successes else None}


def _interval(values):
    ordered = sorted(values)
    def quantile(probability):
        position = (len(ordered) - 1) * probability
        lower = int(position)
        upper = min(lower + 1, len(ordered) - 1)
        return ordered[lower] + (position - lower) * (ordered[upper] - ordered[lower])
    return [quantile(.025), quantile(.975)]


def analyze(rows, *, phase="final", bootstrap_samples=BOOTSTRAP_SAMPLES, seed=BOOTSTRAP_SEED,
            expected_tasks=None, expected_arms=ARMS, expected_histories=None):
    """Paired all-attempt scores; domain-equal macro; clustered conditional CIs.

    Required row fields: phase, task_id, domain, history(int), arm, hard
    (None/0/1), category, request_hash, cluster_id. Question aliases should share
    their original question cluster; task histories and arms are never sampled
    independently. Benchmark task accuracy is the point estimate: average all
    tasks/histories within domain, then weight domains equally. Bootstrap entire
    clusters within domain, retaining all member tasks and observed histories.
    Its task-weighted ratio handles clusters of unequal sizes. Unknown outcomes
    are unsuccessful all-attempt positions, not removed observations.
    """
    if phase not in {"confirmation", "final"}:
        raise ValueError("Analyze only frozen confirmation or final observations")
    if type(bootstrap_samples) is not int or not 1 <= bootstrap_samples <= 10000 or type(seed) is not int:
        raise ValueError("Use a bounded positive draw count and integer seed")
    indexed, metadata, histories, arms, unique_requests = _grid(
        rows, phase, expected_tasks=expected_tasks, expected_arms=expected_arms, expected_histories=expected_histories)
    clusters = {domain: defaultdict(list) for domain in DOMAINS}
    for task, info in sorted(metadata.items()):
        clusters[info["domain"]][info["cluster_id"]].append(task)
    rates, summaries = {}, {}
    for arm in arms:
        domains = {}
        for domain in DOMAINS:
            selected = [row for row in rows if row["arm"] == arm and row["domain"] == domain]
            domains[domain] = {**_counts(selected), "unique_tasks": sum(map(len, clusters[domain].values())),
                               "clusters": len(clusters[domain])}
        rates[arm] = {domain: item["all_attempt_success_rate"] for domain, item in domains.items()}
        summaries[arm] = {**_counts([row for row in rows if row["arm"] == arm]), "by_domain": domains,
                          "macro_success_rate": mean(rates[arm].values()),
                          "worst_domain_success_rate": min(rates[arm].values())}
    rng = random.Random(seed)
    plans = [{domain: [rng.choice(sorted(clusters[domain])) for _ in clusters[domain]] for domain in DOMAINS}
             for _ in range(bootstrap_samples)]
    contrast_pairs = [(arm, "no_skill") for arm in arms if arm != "no_skill" and "no_skill" in arms]
    contrast_pairs += [(arm, "parent") for arm in arms if arm not in {"no_skill", "parent"} and "parent" in arms]
    if "layered" in arms and "whole" in arms:
        contrast_pairs.append(("layered", "whole"))
    comparisons = {}
    for arm, reference in contrast_pairs:
        task_delta = {task: mean([int(indexed[task, history, arm]["hard"] == 1)
                                 - int(indexed[task, history, reference]["hard"] == 1) for history in histories])
                      for task in metadata}
        observed = {domain: rates[arm][domain] - rates[reference][domain] for domain in DOMAINS}
        draws = [{domain: mean([task_delta[task] for cluster in plan[domain] for task in clusters[domain][cluster]])
                  for domain in DOMAINS} for plan in plans]
        domain_result = {domain: {"delta": observed[domain], "ci95": _interval([draw[domain] for draw in draws]),
                                 "paired": _paired([row for row in rows if row["domain"] == domain], indexed, arm, reference)}
                         for domain in DOMAINS}
        by_history = {}
        for history in histories:
            selected = [row for row in rows if row["history"] == history]
            per_domain = {domain: _paired([row for row in selected if row["domain"] == domain], indexed, arm, reference)
                          for domain in DOMAINS}
            by_history[str(history)] = {"by_domain": per_domain,
                "macro_delta": mean(item["delta"] for item in per_domain.values()),
                "paired": _paired(selected, indexed, arm, reference)}
        comparisons[arm + "_vs_" + reference] = {"by_domain": domain_result,
            "macro_delta": mean(observed.values()), "macro_delta_ci95": _interval([mean(draw.values()) for draw in draws]),
            "worst_domain_delta": min(observed.values()),
            "paired": _paired(rows, indexed, arm, reference), "by_history": by_history}
    return {"version": VERSION, "phase": phase, "arms": summaries, "comparisons": comparisons,
            "primary_contrasts": [name for name in ("layered_vs_whole", "core_only_vs_parent") if name in comparisons],
            "histories": histories, "unique_tasks": len(metadata), "complete_grid_positions": len(rows),
            "unique_request_hashes": unique_requests, "domains": list(DOMAINS),
            "bootstrap": {"samples": bootstrap_samples, "seed": seed,
                "unit": "question_or_task_cluster_with_all_member_tasks_and_histories",
                "stratified_by_domain": True, "conditional_on_observed_histories": True,
                "histories_resampled_as_independent_tasks": False, "multiple_comparison_adjustment": False},
            "manifest_checked": all(x is not None for x in (expected_tasks, expected_arms, expected_histories)),
            "unknowns_retained_in_all_attempt_denominator": True,
            "statistical_safety_claim": False}


def empirical_gate(rows, *, candidate_arm="layered", phase="confirmation",
                   expected_tasks=None, expected_histories=None):
    """Approve each domain separately using ONLY one history's confirmation.

    Candidate must have zero paired observed losses against BOTH no_skill and
    parent, and >=1 paired win against EACH within that domain. Any unknown in
    candidate/base/parent prevents that domain's approval. Another domain can
    still be independently approved. All three reference arms are required;
    complete additional arms may be present but cannot influence admission.
    A rejected domain falls back to no_skill, not an assumed-safe parent.
    """
    if phase != "confirmation" or candidate_arm not in {"whole", "core_only", "layered"}:
        raise ValueError("Gate requires confirmation evidence and a declared candidate arm")
    indexed, metadata, histories, arms, _ = _grid(
        rows, "confirmation", expected_tasks=expected_tasks, expected_histories=expected_histories)
    if len(histories) != 1 or not {"no_skill", "parent", candidate_arm}.issubset(arms):
        raise ValueError("Gate one history with candidate, No-Skill and parent anchors")
    support, mapping = {}, {}
    for domain in DOMAINS:
        selected = [row for row in rows if row["domain"] == domain
                    and row["arm"] in {"no_skill", "parent", candidate_arm}]
        counts = {anchor: _paired(selected, indexed, candidate_arm, anchor) for anchor in ("no_skill", "parent")}
        unknown = any(row["hard"] is None for row in selected)
        approved = not unknown and all(item["losses"] == 0 and item["wins"] >= 1 for item in counts.values())
        reason = ("unknown_confirmation_evidence" if unknown else
                  "observed_loss" if any(item["losses"] for item in counts.values()) else
                  "domain_gain_without_observed_losses" if approved else "insufficient_positive_evidence")
        support[domain] = {"approved": approved, "reason": reason, "unknown_evidence": unknown, "against": counts}
        mapping[domain] = candidate_arm if approved else "no_skill"
    return {"version": VERSION, "phase": "confirmation", "history": histories[0],
            "candidate_arm": candidate_arm, "domain_mapping": mapping,
            "approved_domains": [domain for domain in DOMAINS if support[domain]["approved"]],
            "support": support, "unique_tasks": len(metadata), "statistical_safety_claim": False,
            "unseen_domain_default": "no_skill", "routing": "trusted_entry_domain_only",
            "final_outcomes_used_for_routing": False}
