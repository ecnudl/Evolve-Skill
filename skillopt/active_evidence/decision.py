"""The post-update decision (rule v2): frozen before the comparison, applied to the sealed challenge outcome.

Unit of evidence: the FAMILY (net of its jointly known positions in a set: improving, regressing or tied). Test: the
exact ONE-sided sign test on the non-tied families -- gain (improving) and harm (regressing). Precedence (top to
bottom, ``alpha`` from the sealed limits):
  1. no candidate, or a candidate identical to the parent              -> no_update
  2. the arm runs no post-update challenge                             -> accepted_without_challenge
  3. the challenge did not run (no eligible fresh task)                -> park (insufficient evidence)
  4. replay harm significant                                           -> revert
  5. fewer jointly known fresh positions than ``min_paired_known``     -> park (fresh decision inadmissible)
  6. fresh harm significant                                            -> revert
  7. fresh gain significant AND the aggregate guard (task-level net over the jointly known fresh positions strictly
     positive) AND the adverse completion (every unknown-side fresh position counted as a candidate loss: the gain
     test and the guard must still hold)                               -> keep
  8. anything else                                                     -> park
``revert`` = harm was shown on the stated rows; ``park`` = no admissible evidence of gain; both carry the parent.

For ONE candidate-decision step, under the null that -- for each set separately, conditional on the frozen candidate
and all preceding history (for replay also on the historical-pass selection of its rows) -- the observed non-tied
family signs are independent and fair: P(keep) <= alpha and P(revert) <= 2 * alpha (union bound over the two harm
tests). Independence across families is an assumption; no stage-wide or chain-wide guarantee is claimed. For
multi-task families the sign test speaks about family directions, not aggregate accuracy -- hence the guard, which
is an observed-panel requirement, not a significance statement. Replay rows were seen by the analysts: replay is a
harm-only test about those rows. A candidate's unknown position is reported as unknown, never charged as a loss in
the recorded outcome; a missing observation is never a pass. Infrastructure failures -- including a missing budget
reserve for the challenge -- are not decisions: the stage records them as pending, outside this table. Design memo: docs/handoff/active-evidence-decision-v2-design-20261010.md.

In-sample shadow (only when the challenge carries a ``train_panel`` set; never an input of the action above): the
action this table would return with the train panel in place of the fresh panel -- the same replay precedence
(step 4), coverage ceil(90%) of the panel's positions, family tests, guard and adverse completion. The analysts saw
those rows: its p-values are operational heuristics without the fresh panel's error statement, and the agreement of
the shadow with the reserved-pool action is the thing being measured. ``size_matched_fresh`` is the same table on
the first n positions of the sealed fresh draw order (n = panel positions), a sensitivity reading at equal panel
size. Design memo: docs/handoff/active-evidence-in-sample-shadow-design-20261011.md."""
from __future__ import annotations

import difflib

from skillopt.coevolution_v5.core import seal
from skillopt.continual_eval.core import require
from skillopt.validator_pilot.api import digest

RULE_VERSION = "active-evidence-decision-v2"
SHADOW_VERSION = "in-sample-shadow-v1"
ACTIONS = ("no_update", "accepted_without_challenge", "keep", "revert", "park")
ADVANCING = {"accepted_without_challenge", "keep"}
FAMILY_KEYS = ("families", "families_improving", "families_regressing", "families_tied", "families_non_tied",
               "family_p_value", "family_harm_p_value")


def new_hunks(parent, candidate, limit=12):
    """The candidate's text that the parent did not have (what a scoped revision would be confined to)."""
    matcher = difflib.SequenceMatcher(a=parent.splitlines(), b=candidate.splitlines(), autojunk=False)
    hunks = []
    for tag, _, _, j1, j2 in matcher.get_opcodes():
        if tag in {"insert", "replace"}:
            hunks.append("\n".join(candidate.splitlines()[j1:j2]))
    return hunks[:limit]


def _evidence(summary):
    """The decision inputs of one set; a statistic of an empty set is null with its reason."""
    if summary["positions"] == 0:
        return {"positions": 0, "jointly_known": 0, "net_wins": None, **dict.fromkeys(FAMILY_KEYS),
                "unavailable": "no_positions_in_this_set"}
    return {"positions": summary["positions"], "jointly_known": summary["jointly_known"], "net_wins": summary["net_wins"],
            **{k: summary[k] for k in FAMILY_KEYS}}


def panel_action(panel, replay_harm, alpha):
    """Steps 4-8 of the table with ``panel`` in place of the fresh panel (shadow readings only)."""
    adverse = panel["adverse"]
    needed = -(-9 * panel["positions"] // 10)
    flags = {"replay_harm": replay_harm,
             "admissible": panel["positions"] > 0 and panel["jointly_known"] >= needed,
             "harm": panel["positions"] > 0 and panel["family_harm_p_value"] <= alpha,
             "gain": panel["positions"] > 0 and panel["family_p_value"] <= alpha,
             "aggregate_guard": panel["net_wins"] > 0,
             "adverse_completion": adverse["family_p_value"] <= alpha and adverse["net_wins"] > 0}
    if flags["replay_harm"]:
        action, reason = "revert", "replay_harm_significant"
    elif not flags["admissible"]:
        action, reason = "park", "panel_decision_inadmissible"
    elif flags["harm"]:
        action, reason = "revert", "panel_harm_significant"
    elif flags["gain"] and flags["aggregate_guard"] and flags["adverse_completion"]:
        action, reason = "keep", "panel_gain_significant_with_aggregate_guard_and_adverse_completion"
    else:
        action = "park"
        reason = ("panel_gain_not_significant" if not flags["gain"] else
                  "aggregate_guard_not_met" if not flags["aggregate_guard"] else
                  "gain_not_robust_to_unknown_positions")
    return {"action": action, "reason": reason, "flags": flags, "evidence": _evidence(panel),
            "min_paired_known": needed}


def decide(outcome, limits, *, parent, candidate, step):
    """Return the sealed decision record for one step."""
    changed = candidate is not None and candidate != parent
    alpha = limits["decision_alpha_permille"] / 1000
    inputs = {"candidate_changed": changed, "challenge_status": None if outcome is None else outcome["status"]}
    suggestion = shadow = None
    if not changed:
        action, reason = "no_update", "no_candidate_or_identical_to_parent"
    elif outcome is None:
        action, reason = "accepted_without_challenge", "post_update_arm_none"
    elif outcome["status"] != "completed":
        action, reason = "park", "challenge_not_completed:" + str(outcome.get("reason"))
    else:
        fresh, replay, local = (outcome["summary"][k] for k in ("fresh", "replay", "local_fix"))
        adverse = fresh["adverse"]
        flags = {
            "replay_harm": replay["positions"] > 0 and replay["family_harm_p_value"] <= alpha,
            "fresh_admissible": fresh["jointly_known"] >= limits["min_paired_known"],
            "fresh_harm": fresh["positions"] > 0 and fresh["family_harm_p_value"] <= alpha,
            "fresh_gain": fresh["positions"] > 0 and fresh["family_p_value"] <= alpha,
            "aggregate_guard": fresh["net_wins"] > 0,
            "adverse_completion": adverse["family_p_value"] <= alpha and adverse["net_wins"] > 0}
        inputs.update(fresh=_evidence(fresh), replay=_evidence(replay), flags=flags,
                      fresh_adverse={k: adverse[k] for k in ("unknown_positions", "net_wins", "families_improving",
                                                             "families_regressing", "family_p_value")},
                      fresh_candidate_unknown=fresh["candidate_unknown"],
                      replay_regressions=replay["regressions"],
                      local_fix={"positions": local["positions"], "fixed": local["fixed"],
                                 "jointly_known": local["jointly_known"], "decision_input": False})
        if "train_panel" in outcome["summary"]:
            panel, matched = outcome["summary"]["train_panel"], outcome["summary"]["fresh_size_matched"]
            shadow = {"version": SHADOW_VERSION, **panel_action(panel, flags["replay_harm"], alpha), "alpha": alpha,
                      "by_step_status": panel["by_step_status"], "reused_positions": panel["reused_positions"],
                      "size_matched_fresh": ({"action": None, "reason": matched["unavailable"],
                                              "positions": matched["positions"],
                                              "wanted_positions": matched["wanted_positions"]}
                                             if "unavailable" in matched else
                                             panel_action(matched, flags["replay_harm"], alpha)),
                      "note": "in-sample: the analysts saw the known rows; p-values here are operational heuristics; "
                              "recorded to measure agreement with the reserved-pool action, never used by it",
                      "decision_input": False}
        if flags["replay_harm"]:
            action, reason = "revert", "replay_harm_significant"
        elif not flags["fresh_admissible"]:
            action, reason = "park", "fresh_decision_inadmissible"
        elif flags["fresh_harm"]:
            action, reason = "revert", "fresh_harm_significant"
        elif flags["fresh_gain"] and flags["aggregate_guard"] and flags["adverse_completion"]:
            action, reason = "keep", "fresh_gain_significant_with_aggregate_guard_and_adverse_completion"
        else:
            action = "park"
            reason = ("fresh_gain_not_significant" if not flags["fresh_gain"] else
                      "aggregate_guard_not_met" if not flags["aggregate_guard"] else
                      "gain_not_robust_to_unknown_positions")
            if replay["regressions"]:
                suggestion = {"kind": "restrict_scope_of_new_text", "regressions": replay["regressions"],
                              "new_hunks": new_hunks(parent, candidate), "deferred": True}
    require(action in ACTIONS, "Unknown decision action")
    return seal({"rule_version": RULE_VERSION, "step": step, "action": action, "reason": reason, "inputs": inputs,
                 "limits": {"min_paired_known": limits["min_paired_known"], "alpha": alpha},
                 "unit": "family (net of its jointly known positions); exact one-sided sign tests on non-tied families",
                 "error_statement": "one candidate-decision step, conditional nulls of independent fair non-tied family "
                                    "signs per set: P(keep) <= alpha, P(revert) <= 2 alpha; no stage- or chain-wide "
                                    "guarantee",
                 "candidate_hash": digest(candidate) if changed else None,
                 "outcome_hash": None if outcome is None else outcome["record_hash"],
                 "next_skill": "candidate" if action in ADVANCING else "parent",
                 "restriction_suggested": suggestion,
                 **({} if shadow is None else {"in_sample_shadow": shadow}),
                 "unknown_semantics": "candidate unknown reported, never a loss in the recorded outcome; keep must "
                                      "survive the adverse completion; missing evidence never a pass",
                 "deployment_authorized": False})
