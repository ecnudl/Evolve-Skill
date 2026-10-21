"""Matched-branch study (``post_update = "matched_scalar_branch"``): the same bound traces feed two updater branches
-- the comparator S (the scalar arm's exact analyst package) and the treatment M (the arm's evidence package) --
and both frozen candidates solve the same drawn development holdout. Nothing is deployed; the step's decision record
compares M ("candidate") with S ("current") through the ordinary paired machinery, and this module adds the
prespecified outcome class with its statistics. Estimand: the paired pass difference (M minus S) on JOINTLY KNOWN
holdout positions; interval = Tango's (1998) score interval for a paired difference of proportions (valid with
sparse or zero discordance; reduces to McNemar at zero); test = exact two-sided sign test on discordant pairs.
Unknowns are counted and bounded in a worst-case sensitivity, never imputed. One realized candidate pair, one
training history, a reused development pool: exploratory (design memo of 2026-10-10, Codex rounds 1-4).

Study v2 adds evaluation-only REFERENCE Skills on the same drawn holdout (``challenge.run_references``): the stage's
parent (does a no-validation update beat no update at all?) and optional sealed Skills such as the one a
validation-gated baseline stage deployed (is the no-validation branch non-inferior to it?). Each branch-minus-reference
comparison gets the same statistics and class as the primary contrast, plus a non-inferiority flag at the useful-gain
margin; the three-plus comparisons are descriptive (no multiplicity adjustment) and reference batches run after the
two branches (service drift between batches is not excluded)."""
from __future__ import annotations

import difflib
import math
from math import comb

from skillopt.validator_pilot.api import digest

OUTCOMES = ("failed_delivery", "useful_gain", "harmful_change", "inconclusive")
USEFUL_GAIN_FRACTION = 0.05  # paired pass-rate difference on jointly known positions
MAX_UNKNOWN_FRACTION = 0.10  # of drawn positions; above it the step is a failed delivery of the evaluation
ALPHA = 0.05
Z = 1.959964
INTERVAL = "tango-1998-score-interval-paired-difference"
STUDY_VERSION = "matched-scalar-branch-study-v2"  # v2: holdout reference Skills (parent, sealed baselines)


MIN_CHECKED_CASE_FRACTION = 0.5  # of the attempted diagnosis cases; below it the treatment package is not delivered


def treatment_delivery_problem(diagnosis):
    """Why the treatment branch's feedback package does not count as delivered (None when it does). The study must
    not spend two updater branches and the holdout on a treatment that is the scalar package in disguise: a
    diagnosis that did not complete, attached no row report, or lost more than half of its attempted cases to
    format failures stops the step pending BEFORE any updater call. Pending / not-applicable items are legitimate
    results, not delivery failures. The failure-message arm carries its own sealed release audit (no ``delivery``)."""
    if diagnosis["status"] != "completed":
        return "diagnosis_" + diagnosis["status"].split(":")[0]
    delivery = diagnosis.get("delivery")
    if delivery is None:
        return None
    if delivery["rows_with_reports"] == 0:
        return "no_row_report"
    if delivery["cases_format_failed"] > (1 - MIN_CHECKED_CASE_FRACTION) * delivery["cases_attempted"]:
        return "format_failures_exceed_half_of_attempted_cases"
    return None


def comparator_traces(traces):
    """The scalar package: identical traces without any evidence text."""
    return [{**t, "Feedback": {k: v for k, v in t["Feedback"].items() if k != "evidence"}} for t in traces]


def sign_test_p(wins, losses):
    """Exact TWO-sided sign test on discordant pairs (the frozen ``skillopt.sign_test_p`` is one-sided)."""
    n, k = wins + losses, min(wins, losses)
    if n == 0:
        return 1.0
    return min(1.0, 2 * sum(comb(n, i) for i in range(k + 1)) / 2 ** n)


def tango_score(wins, losses, known, delta):
    """Tango's score statistic for H0: paired difference = ``delta`` (restricted MLE of the loss-type discordant
    probability; at delta = 0 this is the McNemar statistic (b - c) / sqrt(b + c))."""
    n, b, c = known, wins, losses
    a_, b_ = 2 * n, -b - c + (2 * n - b + c) * delta
    c_ = -c * delta * (1 - delta)
    p21 = (math.sqrt(max(b_ * b_ - 4 * a_ * c_, 0.0)) - b_) / (2 * a_)
    variance = n * (2 * p21 + delta * (1 - delta))
    numerator = b - c - n * delta
    if variance <= 0:
        return math.inf if numerator > 0 else -math.inf if numerator < 0 else 0.0
    return numerator / math.sqrt(variance)


def paired_difference(wins, losses, known):
    """Point estimate and Tango 95% score interval of the paired difference (M minus S) over ``known`` positions;
    the statistic is monotone decreasing in delta, so each bound is found by bisection."""
    if known == 0:
        return {"estimate": None, "ci95": None, "interval": INTERVAL}
    estimate = (wins - losses) / known

    def bisect(lo, hi, target):
        for _ in range(80):
            mid = (lo + hi) / 2
            if tango_score(wins, losses, known, mid) > target:
                lo = mid
            else:
                hi = mid
        return (lo + hi) / 2
    lower = bisect(-1.0 + 1e-9, estimate, Z)
    upper = bisect(estimate, 1.0 - 1e-9, -Z)
    return {"estimate": round(estimate, 6), "ci95": [round(lower, 6), round(upper, 6)], "interval": INTERVAL}


def paired_class(wins, losses, ties, positions, min_paired_known, *, estimand):
    """Statistics and prespecified class of one paired contrast (first-named side minus second) over ``positions``
    drawn holdout positions of which wins + losses + ties are jointly known."""
    known = wins + losses + ties
    unknown = positions - known
    p = sign_test_p(wins, losses)
    diff = paired_difference(wins, losses, known)
    # worst case for the first-named side: every unknown position counted as its loss (sensitivity, not estimate)
    worst = paired_difference(wins, losses + unknown, known + unknown)
    low, high = diff["ci95"] if diff["ci95"] is not None else (None, None)
    stats = {"estimand": estimand,
             "independence_assumption": "one task per family by construction; family independence is assumed by the "
                                        "sign test and the interval; semantic independence is not audited",
             "positions": positions, "jointly_known": known, "unknown_positions": unknown,
             "wins": wins, "losses": losses, "ties": ties, "net_wins": wins - losses, "discordant": wins + losses,
             "sign_test_two_sided_p": round(p, 6), "difference": diff, "useful_gain": USEFUL_GAIN_FRACTION,
             "worst_case_unknowns_as_treatment_losses": worst,
             # "not more than `margin` worse": the whole interval above minus the margin. `holds` speaks about the
             # jointly known positions only; a statement about the whole draw needs `holds_with_unknowns_as_losses`
             # (every unknown counted as a loss of the first-named side). Not holding never establishes inferiority.
             "non_inferiority": {"margin": USEFUL_GAIN_FRACTION,
                                 "holds": low is not None and low > -USEFUL_GAIN_FRACTION,
                                 "holds_with_unknowns_as_losses": worst["ci95"] is not None
                                 and worst["ci95"][0] > -USEFUL_GAIN_FRACTION,
                                 "scope": "jointly known positions of this contrast"}}
    if known < min_paired_known or unknown > MAX_UNKNOWN_FRACTION * positions:
        # the descriptive statistics and the sensitivity bound are still reported; no class beyond failed delivery
        return not_measured({"outcome": "failed_delivery", **stats}, "insufficient_jointly_known_holdout_pairs")
    if known == 0:
        return not_measured({"outcome": "failed_delivery", **stats}, "no_jointly_known_holdout_pairs")
    if diff["estimate"] >= USEFUL_GAIN_FRACTION and p <= ALPHA and low > 0:
        robust = worst["estimate"] >= USEFUL_GAIN_FRACTION and worst["ci95"][0] > 0
        return {"outcome": "useful_gain", "reason": "difference_at_or_above_useful_gain_with_interval_above_zero",
                "robust_to_unknowns": robust, **stats}
    if diff["estimate"] <= -USEFUL_GAIN_FRACTION and p <= ALPHA and high < 0:
        return {"outcome": "harmful_change", "reason": "difference_at_or_below_minus_useful_gain_with_interval_below_zero",
                **stats}
    reason = "worthwhile_gain_excluded" if high < USEFUL_GAIN_FRACTION else "interval_includes_both"
    return {"outcome": "inconclusive", "reason": reason, **stats}


def not_measured(result, reason):
    """A contrast that was not measured: class ``failed_delivery`` with ``reason``; the counts and intervals stay as
    descriptive diagnostics, and neither non-inferiority flag can hold."""
    out = {**result, "outcome": "failed_delivery", "reason": reason}
    out.pop("robust_to_unknowns", None)
    if "non_inferiority" in out:
        out["non_inferiority"] = {**out["non_inferiority"], "holds": False, "holds_with_unknowns_as_losses": False}
    return out


def outcome_class(fresh, *, delivered, candidates_identical, treatment_ready, min_paired_known):
    """The prespecified class of one matched study step (design memo v4, sections A1-A2)."""
    if not delivered or candidates_identical or not treatment_ready:
        return {"outcome": "failed_delivery", "reason": ("release_below_minimum" if not delivered
                                                          else "treatment_proposal_not_ready" if not treatment_ready
                                                          else "identical_candidates")}
    if fresh is None:
        return {"outcome": "failed_delivery", "reason": "holdout_not_evaluated"}
    return paired_class(fresh["wins"], fresh["losses"], fresh["ties"], fresh["positions"], min_paired_known,
                        estimand="paired pass difference (treatment minus comparator) on jointly known holdout positions")


def reference_comparisons(references, parent, min_paired_known, *, branches):
    """Per reference Skill: its pass count on the holdout and the class of each branch minus it. The parent answers
    'does the update beat no update'; a sealed baseline Skill answers 'is the branch not much worse than it'.
    ``branches`` maps comparator/treatment to {"skill_hash", "updated"}: a branch whose Skill is the unchanged parent
    (no candidate), or is identical to the reference it is compared with, is NOT a measured contrast -- its counts are
    kept as descriptive diagnostics (a same-Skill pair is a noise replicate) under ``failed_delivery``. The same holds
    for a named reference identical to the parent in its instrument check."""
    if references is None or references["status"] != "completed":
        return None
    parent_hash = digest(parent)
    result = {}
    for entry in references["references"]:
        name, summary = entry["name"], references["summary"][entry["name"]]
        row = {"skill_hash": entry["skill_hash"], "is_parent": name == "parent", "rollout": entry["rollout"],
               "pass": summary["pass"], "fail": summary["fail"], "unknown": summary["unknown"]}
        for branch in ("comparator", "treatment"):
            counts = summary[branch + "_minus_reference"]
            measured = paired_class(
                counts["wins"], counts["losses"], counts["ties"], counts["positions"], min_paired_known,
                estimand=f"paired pass difference ({branch} branch minus reference '{name}') on jointly known holdout "
                         "positions")
            # an updater branch that produced no update is not a measured arm; a DELIVERED SELECTION (the selection
            # study's treatment) is one even when it is the parent text -- only its same-text pairs are replicates
            if not branches[branch]["updated"] and not branches[branch].get("delivered_selection"):
                measured = not_measured(measured, "branch_skill_unchanged_from_parent")
            elif branches[branch]["skill_hash"] == entry["skill_hash"]:
                measured = not_measured(measured, "branch_skill_identical_to_reference")
            row[branch + "_minus_reference"] = measured
        if "reference_minus_parent" in summary:
            counts = summary["reference_minus_parent"]
            measured = paired_class(
                counts["wins"], counts["losses"], counts["ties"], counts["positions"], min_paired_known,
                estimand=f"paired pass difference (reference '{name}' minus the parent) on jointly known holdout "
                         "positions (instrument check: a known effect of the reference should be visible here)")
            if entry["skill_hash"] == parent_hash:
                measured = not_measured(measured, "reference_identical_to_parent")
            row["reference_minus_parent"] = measured
            # the memo's instrument condition, exposed so a report never shows a non-inferiority flag without it
            visible = measured["outcome"] == "useful_gain"
            row["q3_interpretable"] = {"holds": visible, "reason": "instrument_check_useful_gain" if visible else
                                       "instrument_check_" + measured["outcome"] + ":" + measured["reason"]}
        result[name] = row
    return {"references_hash": references["record_hash"],
            "parent_bound": "parent" in result and result["parent"]["skill_hash"] == parent_hash,
            "branch_pass": references["branch_pass"], "branches": branches, "by_reference": result,
            "note": "evaluation-only references on the same drawn holdout; exploratory contrasts without multiplicity "
                    "adjustment; reference batches ran after the two branches (not interleaved); a contrast between "
                    "two copies of the SAME text is a noise replicate, never a measured effect; an updater branch that "
                    "produced no update is not a measured arm, while a delivered selection (selection study) is one "
                    "even when it is the parent text"}


def skill_diff_lines(before, after):
    return sum(1 for line in difflib.unified_diff(before.splitlines(), after.splitlines(), lineterm="", n=0)
               if line[:1] in "+-" and not line.startswith(("+++", "---")))


def _edits(proposal):
    selected = proposal.get("selected")
    return len(selected["edits"]) if type(selected) is dict and type(selected.get("edits")) is list else None


def _branch(proposal, skill):
    return {"proposal_hash": proposal["record_hash"], "status": proposal["status"],
            "skill_hash": None if skill is None else digest(skill),
            # the adapter keys every holdout evaluation request by digest({"skill": ...}): the join to the receipts
            "request_candidate_hash": None if skill is None else digest({"skill": skill}),
            "skill_bytes": None if skill is None else len(skill.encode("utf-8")),
            "edit_count": _edits(proposal), "native_fallbacks": proposal.get("native_fallbacks", [])}


def matched_record(comparator, comparator_skill, parent, proposal, candidate, outcome, diagnosis, limits,
                   references=None):
    """The sealed study record of one step: both branches, their difference, the delivery audit summary, the
    prespecified outcome class (the holdout's paired summary is the ordinary challenge ``fresh`` set) and, when the
    holdout was evaluated, each branch against the evaluation-only reference Skills."""
    fresh = outcome["summary"]["fresh"] if outcome is not None and outcome["status"] == "completed" else None
    identical = candidate is not None and candidate == comparator_skill
    return {"study": STUDY_VERSION,
            "comparator": {**_branch(comparator, comparator_skill), "is_parent": comparator_skill == parent},
            "treatment": _branch(proposal, candidate),
            "candidates_identical": identical,
            "diff_lines": None if candidate is None else skill_diff_lines(comparator_skill, candidate),
            "delivery": {"status": diagnosis["status"], "release_profile": diagnosis.get("release_profile"),
                         "denominators": diagnosis.get("release_denominators"),
                         "message_classes": diagnosis.get("message_classes"),
                         "diagnosis": diagnosis.get("delivery"), "problem": treatment_delivery_problem(diagnosis)},
            "holdout": None if fresh is None else {k: fresh[k] for k in ("positions", "jointly_known", "wins", "losses",
                                                                           "ties", "candidate_unknown", "current_unknown",
                                                                           "both_unknown", "family_p_value")},
            "holdout_note": "challenge 'fresh' set drawn from the REUSED development pool (earlier stages' fresh draws "
                            "overlap it; the zero-call report records the overlap per prior stage) after both candidates "
                            "were frozen; one task per family by construction -- family independence is an assumption of "
                            "the sign test and the interval, semantic independence is not audited; family_p_value is the "
                            "frozen one-sided sign test, not used for the outcome class",
            "outcome": outcome_class(fresh, delivered=treatment_delivery_problem(diagnosis) is None,
                                     candidates_identical=identical,
                                     treatment_ready=proposal["status"] == "candidate_ready",
                                     min_paired_known=limits["min_paired_known"]),
            "references": reference_comparisons(references, parent, limits["min_paired_known"], branches={
                "comparator": {"skill_hash": digest(comparator_skill),
                               "updated": comparator["status"] == "candidate_ready" and comparator_skill != parent},
                "treatment": {"skill_hash": None if candidate is None else digest(candidate),
                              "updated": proposal["status"] == "candidate_ready" and candidate is not None
                              and candidate != parent}})}


SELECTION_STUDY_VERSION = "matched-selection-branch-study-v3"


def selection_record(proposal, native_candidate, parent, treatment, screen, outcome, limits, references=None,
                     diagnosis=None):
    """The sealed record of one selection-study step (``post_update = "matched_selection_branch"``): comparator = the
    native updater's candidate, treatment = the exact text the composition-aware screen selected -- the candidate
    itself (policy agreement: the pair is a same-Skill replicate, not a measured contrast), a leave-one-edit-out
    variant, or the parent on abstention (a MEASURED contrast: abstaining against updating). One rollout, one
    diagnosis, one native proposal; the contrast supports or fails to support this realized pipeline, not the
    individual edit attributions of the screen (training selection on analyst-seen rows)."""
    fresh = outcome["summary"]["fresh"] if outcome is not None and outcome["status"] == "completed" else None
    identical = native_candidate is not None and treatment == native_candidate
    if native_candidate is None:
        measured = {"outcome": "failed_delivery", "reason": "no_native_candidate"}
    elif fresh is None:
        measured = {"outcome": "failed_delivery", "reason": "holdout_not_evaluated"}
    else:
        measured = paired_class(fresh["wins"], fresh["losses"], fresh["ties"], fresh["positions"],
                                limits["min_paired_known"],
                                estimand="paired pass difference (screen selection minus native candidate) on jointly "
                                         "known holdout positions")
        if identical:
            measured = not_measured(measured, "policy_agreement_same_skill_replicate")
    selection = None if screen is None else screen["record"]["selection"]
    return {"study": SELECTION_STUDY_VERSION,
            "comparator": {**_branch(proposal, native_candidate), "role": "native candidate", "is_parent": False},
            "treatment": {"role": "screen selection", "selection": selection,
                          "skill_hash": None if treatment is None else digest(treatment),
                          "request_candidate_hash": None if treatment is None else digest({"skill": treatment}),
                          "skill_bytes": None if treatment is None else len(treatment.encode("utf-8")),
                          "is_parent": treatment is not None and treatment == parent,
                          "identical_to_comparator": identical},
            "candidates_identical": identical,
            "diff_lines": None if treatment is None or native_candidate is None
            else skill_diff_lines(native_candidate, treatment),
            "screen": None if screen is None else {"outcome_hash": screen["record"]["record_hash"],
                                                   "inventory_hash": screen["inventory_hash"]},
            "delivery": {"status": "completed" if native_candidate is not None else "no_native_candidate",
                         "problem": None if native_candidate is not None else "no_native_candidate",
                         # the feedback package the shared native proposal was built from (not gated in this study:
                         # the contrast is between two selections from the same proposal)
                         "diagnosis_status": None if diagnosis is None else diagnosis["status"],
                         "diagnosis": None if diagnosis is None else diagnosis.get("delivery"),
                         "diagnosis_problem": None if diagnosis is None or diagnosis["status"] == "scalar_arm_no_diagnosis"
                         else treatment_delivery_problem(diagnosis)},
            "holdout": None if fresh is None else {k: fresh[k] for k in ("positions", "jointly_known", "wins", "losses",
                                                                           "ties", "candidate_unknown", "current_unknown",
                                                                           "both_unknown", "family_p_value")},
            "holdout_note": "drawn development holdout (reused pool) after both texts were frozen; the two branches in a "
                            "balanced order, the parent and named references after them (not interleaved); statistics "
                            "assume one task per family",
            "outcome": measured,
            "references": None if native_candidate is None else reference_comparisons(
                references, parent, limits["min_paired_known"], branches={
                    "comparator": {"skill_hash": digest(native_candidate), "updated": native_candidate != parent},
                    "treatment": {"skill_hash": digest(treatment), "updated": treatment != parent,
                                  "delivered_selection": True}})}
