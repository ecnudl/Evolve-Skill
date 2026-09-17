"""Pure Coding transfer statistics and an exploratory, family-controlled gate.

Question clusters, not shared policy/history positions, are independent units.
No-Skill fallback is an exact shared request, never credited as learned benefit.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from copy import deepcopy

from skillopt.coevolution_v5.core import seal
from skillopt.coevolution_v9 import analysis as paired

POLICIES = ("no_skill", "initial", "raw_transfer", "scope_gated")
_INTERNAL = {"raw_transfer": "skillopt", "scope_gated": "ours"}
_EXTERNAL = {value: key for key, value in _INTERNAL.items()}


def _internal(row):
    if row.get("policy") not in POLICIES:
        raise ValueError("Unexpected Coding policy")
    fields = ("task_id", "cluster_id", "history", "request_hash", "skill_hash", "api_ok")
    return {key: row[key] for key in fields} | {"policy": _INTERNAL.get(row["policy"], row["policy"]),
        "em": row["hard"], "f1": row["soft"]}


def _external(value):
    """Rename internal generic paired-statistic slots; never call Coding EM/F1."""
    names = {"em": "task_success", "f1": "assertion_fraction",
             "all_attempt_em": "all_attempt_task_success", "all_attempt_f1": "all_attempt_assertion_fraction",
             "available_only_em_diagnostic": "available_only_task_success_diagnostic",
             "available_only_f1_diagnostic": "available_only_assertion_fraction_diagnostic",
             "question_cluster_equal_em": "question_cluster_equal_task_success",
             "question_cluster_equal_f1": "question_cluster_equal_assertion_fraction",
             "history_em_delta_range": "history_task_success_delta_range",
             "primary_em_holm_adjusted_p": "primary_holm_adjusted_p",
             "evolved_skill_positions": "noninitial_positions_not_learned_usage"}
    if isinstance(value, dict):
        return {_external(names.get(key, key)): _external(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_external(item) for item in value]
    if isinstance(value, str):
        if "_vs_" in value:
            return "_vs_".join(_EXTERNAL.get(part, part) for part in value.split("_vs_"))
        return _EXTERNAL.get(value, value)
    return value


def summarize_final(rows, *, expected_tasks, histories, bootstrap_samples=5000):
    internal = [_internal(row) for row in rows]
    original = paired.summarize_final(internal, expected_tasks=expected_tasks, histories=histories,
                                       bootstrap_samples=bootstrap_samples, seed=20260914)
    keys = ("n_questions", "n_question_clusters", "histories", "n_observation_positions",
            "unique_actual_requests", "aliased_positions_beyond_first_request", "policy_summary", "comparisons")
    result = _external({key: original[key] for key in keys})
    result.update(primary_metric="supported_native_assertions_all_pass", secondary_metric="assertion_pass_fraction",
        main_multiplicity=_external(original["primary_em_multiplicity"]),
        source_skill_domain="searchqa", measured_domain="coding", canonical_mbpp_reproduction=False,
        reused_v9_pairing_only_not_searchqa_scoring=True, skill_text_verified_by_this_module=False,
        inference_conditional_on_frozen_source_histories=True,
        unknowns_zero_only_for_all_attempt_summary=True, fallback_is_not_skill_generalization=True,
        cross_domain_generalization_established=False, safety_or_noninferiority_certified=False)
    return result


def portfolio_gate(rows, *, expected_tasks, source_skills, minimum_clusters=64,
                   alpha=0.10, maximum_observed_loss_rate=0.02):
    """One shared panel, Holm over all distinct genuinely learned source Skills.

The native initial placeholder is never considered a learned transfer candidate.
No task evidence is returned to an optimizer. Approval is restricted to the
predeclared Coding compatibility population; not an unrestricted scope proof.
"""
    if (not isinstance(source_skills, Mapping) or not source_skills
            or type(minimum_clusters) is not int or minimum_clusters < 64
            or type(alpha) not in (float, int) or not 0 < alpha <= 0.10
            or type(maximum_observed_loss_rate) not in (float, int)
            or not 0 <= maximum_observed_loss_rate <= 0.02):
        raise ValueError("Use explicit bounded preregistered transfer thresholds")
    histories = sorted(source_skills)
    if any(type(h) is not int or h < 0 for h in histories):
        raise ValueError("Source histories must be nonnegative integers")
    for value in source_skills.values():
        if (set(value) != {"skill_hash", "learned"} or not paired._hash(value["skill_hash"])
                or type(value["learned"]) is not bool):
            raise ValueError("A frozen source Skill hash and actual learned flag are required")
    if any(row.get("policy") not in {"no_skill", "initial", "raw_transfer"} for row in rows):
        raise ValueError("The gate accepts exactly its three actual confirmation conditions")
    # Reuse the audited complete-grid/alias validation: the temporary 'ours'
    # slot is an exact base alias, not a generated fourth confirmation arm.
    augmented = [_internal(row) for row in rows]
    augmented.extend({**row, "policy": "ours"} for row in augmented.copy() if row["policy"] == "no_skill")
    indexed, tasks, _, _, _ = paired._validate(augmented, expected_tasks, histories, paired.POLICIES)
    if len(set(tasks.values())) != len(tasks):
        raise ValueError("Transfer confirmation requires one question per independent cluster")
    base_hashes = {indexed[task, h, "no_skill"]["skill_hash"] for task in tasks for h in histories}
    initial_hashes = {indexed[task, h, "initial"]["skill_hash"] for task in tasks for h in histories}
    if base_hashes & initial_hashes:
        raise ValueError("Initial placeholder and empty No-Skill are distinct controls")
    for task in tasks:
        for control in ("no_skill", "initial"):
            if len({indexed[task, h, control]["request_hash"] for h in histories}) != 1:
                raise ValueError("Controls must share their exact same-task requests across histories")
    stats, p_values, first_by_skill = {}, {}, {}
    for history in histories:
        spec = source_skills[history]
        pairs = [(indexed[task, history, "skillopt"], indexed[task, history, "no_skill"]) for task in sorted(tasks)]
        if {row[0]["skill_hash"] for row in pairs} != {spec["skill_hash"]}:
            raise ValueError("Confirmation used a different source Skill")
        if spec["learned"] and spec["skill_hash"] in (base_hashes | initial_hashes):
            raise ValueError("An empty/initial placeholder cannot be labeled learned")
        if not spec["learned"] and {spec["skill_hash"]} != initial_hashes:
            raise ValueError("Unlearned source history must retain the frozen initial placeholder")
        wins = sum(paired._number(a, "em") > paired._number(b, "em") for a, b in pairs)
        losses = sum(paired._number(a, "em") < paired._number(b, "em") for a, b in pairs)
        n = wins + losses
        p = sum(math.comb(n, k) for k in range(wins, n + 1)) / 2**n if n else 1.0
        raw = paired._rates([a for a, _ in pairs])
        base = paired._rates([b for _, b in pairs])
        row = {"history": history, "skill_hash": spec["skill_hash"], "learned": spec["learned"],
            "wins": wins, "losses": losses, "ties": len(pairs) - n,
            "all_attempt_delta": raw["all_attempt_em"] - base["all_attempt_em"],
            "candidate": _external(raw), "base": _external(base),
            "observed_loss_rate": losses / len(pairs),
            "confirmed_scored_losses": sum(a["em"] == 0 and b["em"] == 1 for a, b in pairs),
            "raw_one_sided_p": p}
        if spec["learned"]:
            if spec["skill_hash"] in first_by_skill:
                previous = first_by_skill[spec["skill_hash"]]
                if any(indexed[t, history, "skillopt"]["request_hash"] !=
                       indexed[t, previous, "skillopt"]["request_hash"] for t in tasks):
                    raise ValueError("Repeated identical Skill must share exact confirmation requests")
            else:
                first_by_skill[spec["skill_hash"]] = history
                p_values[spec["skill_hash"]] = p
        stats[history] = row
    adjusted = paired._holm(p_values)
    for history, row in stats.items():
        reasons = []
        if not row["learned"]:
            reasons.append("not_a_learned_source_skill")
        if len(tasks) < minimum_clusters:
            reasons.append("insufficient_independent_target_questions")
        if row["all_attempt_delta"] <= 0:
            reasons.append("no_positive_observed_target_gain")
        value = adjusted.get(row["skill_hash"], 1.0)
        if value > alpha:
            reasons.append("family_adjusted_transfer_evidence_insufficient")
        if row["observed_loss_rate"] > maximum_observed_loss_rate:
            reasons.append("observed_target_loss_screen_exceeded")
        if row["candidate"]["unknown"] > row["base"]["unknown"]:
            reasons.append("candidate_availability_worse_than_base")
        row.update(holm_one_sided_p=value, approve=not reasons, reasons=reasons,
                   action="Commit target-compatible scope" if not reasons else "Restrict; fallback No-Skill")
    return seal({"version": "v10-shared-target-portfolio-gate-v1", "n_questions": len(tasks),
        "minimum_clusters": minimum_clusters, "alpha": alpha,
        "maximum_observed_loss_rate": maximum_observed_loss_rate,
        "family": sorted(p_values), "decisions": {str(h): deepcopy(row) for h, row in stats.items()},
        "same_target_panel_shared_across_histories": True, "per_task_labels_returned": False,
        "optimizer_feedback_authorized": False, "unrestricted_cross_domain_commit_authorized": False,
        "safety_or_noninferiority_certified": False,
        "authorization_population": "predeclared_mbpp_compatible_subset_only"})
