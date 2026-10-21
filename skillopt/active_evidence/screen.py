"""The composition-aware screen (``update_mode = "screened"``): which EXACT Skill text should this step put forward?

After the native proposal (reflection -> merge -> rank -> apply, sealed once) the screen measures exact texts on the
step rows with the native scorer: the native candidate, each leave-one-applied-edit-out variant (the parent with every
other applied edit re-applied in order -- no generative step), and the parent twice (an A/A control). Arms are
interleaved in seeded blocks so controls and variants share the same time window. One measured text is selected by a
frozen rule, or the screen abstains (the parent).

This is TRAINING SELECTION on analyst-seen rows: a search heuristic that decides which text reaches the outer
decision, never an effect estimate and never a validation of individual edits. The p-values are a screening
threshold. Information: native pass/fail of the solver's own outputs on development step rows (more scorer queries per
row); no reference answer, hidden-test text or traceback enters any prompt, and nothing about the challenge pool is
used. Design contract: docs/handoff/active-evidence-screen-design-20261011.md."""
from __future__ import annotations

import random
import re

from skillopt.coevolution_v5.core import seal
from skillopt.continual_eval.core import read_json, require, write_json
from skillopt.continual_learning.contracts import check_skill, skill_budget
from skillopt.continual_learning.ledger import BudgetExhausted, LearningPending
from skillopt.validator_pilot.api import digest

from . import PROTOCOL
from .challenge import _family_counts, _status
from .protocol import min_known

SCREEN_VERSION = "composition-aware-screen-v2"  # v2: single-edit arms, jointly-known coverage, text audit
SELECTION_RULE = "screen-selection-v2"
SCREEN_BASE = 2000  # rollout keys 2000 + 100 * step + arm: disjoint from step keys (0..99) and challenge keys (1000..1999)
BLOCK_ROWS = 16
MAX_DROP_VARIANTS = 8
CONTROLS = ("parent_a", "parent_b")
NOTE = ("training selection on analyst-seen step rows (a search heuristic): not an effect estimate, not a validation "
        "of individual edits; p-values are a screening threshold")


def screen_rollout(step, arm):
    require(type(step) is int and 0 <= step <= 99 and type(arm) is int and 0 <= arm <= 99, "Screen rollout key out of range")
    return SCREEN_BASE + 100 * step + arm


def max_positions(rows, edit_budget):
    """The most native positions one screen can use: two controls, the candidate, and per applied edit one
    leave-one-out and one single-edit variant."""
    return (len(CONTROLS) + 1 + 2 * min(edit_budget, MAX_DROP_VARIANTS)) * rows


def _seed(value, step, name):
    return int(digest({"manifest_hash": value["record_hash"], "step": step, "screen": name})[:16], 16)


def build_arms(parent, proposal, budget_bytes):
    """The arms of one screen with their exact texts and dispositions. A variant that cannot be re-applied cleanly,
    equals the parent, exceeds the Skill budget or repeats another variant's text is recorded and not scored."""
    from skillopt.optimizer.skill import apply_patch_with_report

    edits = proposal["selected"]["edits"]
    candidate = proposal["candidate_skill"]
    rebuilt, report = apply_patch_with_report(parent, {"edits": edits})
    require(rebuilt == candidate and report == proposal["application"],
            "The native candidate is not the parent with its recorded selection applied")
    applied = [i for i, row in enumerate(report) if str(row["status"]).startswith("applied")]
    arms = [{"id": name, "kind": "parent", "dropped_edit": None, "retained_edits": [], "skill": parent,
             "application": None, "disposition": "scored", "alias_of": None} for name in CONTROLS]
    arms.append({"id": "candidate", "kind": "candidate", "dropped_edit": None, "retained_edits": applied,
                 "skill": candidate, "application": report, "disposition": "scored", "alias_of": None})
    if len(applied) >= 2:
        for index in applied[:MAX_DROP_VARIANTS]:
            # only the edits that were APPLIED in the native candidate are re-applied (an edit the native application
            # skipped must not come alive because another edit is gone); each must apply exactly as it did in the full
            # candidate -- a different status (e.g. a fallback caused by the dropped edit's absence) is a dependency,
            # not a clean leave-one-out
            kept = [i for i in applied if i != index]
            text, variant_report = apply_patch_with_report(parent, {"edits": [edits[i] for i in kept]})
            clean = (len(variant_report) == len(kept)
                     and all(row["status"] == report[i]["status"] for i, row in zip(kept, variant_report)))
            arm = {"id": f"drop_{index}", "kind": "leave_one_out", "dropped_edit": index, "retained_edits": kept,
                   "skill": text, "application": variant_report, "disposition": "scored", "alias_of": None}
            if not clean:
                arm["disposition"] = "application_dependency_failed"
            elif text == parent:
                arm["disposition"] = "noop_equals_parent"
            elif len(text.encode("utf-8")) > budget_bytes:
                arm["disposition"] = "exceeds_skill_budget"
            else:
                twin = next((a["id"] for a in arms if a["kind"] != "parent" and a["disposition"] == "scored"
                             and a["skill"] == text), None)
                if twin is not None:
                    arm["disposition"], arm["alias_of"] = "duplicate_text", twin
            arms.append(arm)
        if len(applied) >= 3:
            # with three or more applied edits a single-edit text is not already a leave-one-out variant: each edit
            # ALONE on the parent (does this one hypothesis carry the effect?). An edit that needs another one to apply
            # as recorded is a dependency, as above.
            for index in applied[:MAX_DROP_VARIANTS]:
                text, variant_report = apply_patch_with_report(parent, {"edits": [edits[index]]})
                arm = {"id": f"only_{index}", "kind": "single_edit", "dropped_edit": None, "retained_edits": [index],
                       "skill": text, "application": variant_report, "disposition": "scored", "alias_of": None}
                if not (len(variant_report) == 1 and variant_report[0]["status"] == report[index]["status"]):
                    arm["disposition"] = "application_dependency_failed"
                elif text == parent:
                    arm["disposition"] = "noop_equals_parent"
                elif len(text.encode("utf-8")) > budget_bytes:
                    arm["disposition"] = "exceeds_skill_budget"
                else:
                    twin = next((a["id"] for a in arms if a["kind"] != "parent" and a["disposition"] == "scored"
                                 and a["skill"] == text), None)
                    if twin is not None:
                        arm["disposition"], arm["alias_of"] = "duplicate_text", twin
                arms.append(arm)
    for position, arm in enumerate(arms):
        arm.update(arm=position, skill_hash=digest(arm["skill"]), skill_bytes=len(arm["skill"].encode("utf-8")),
                   request_candidate_hash=digest({"skill": arm["skill"]}))
    return arms


def _schedule(value, step, rows, arm_ids):
    """Seeded blocks of rows; within each block the scored arms in a seeded random order."""
    order = list(range(rows))
    random.Random(_seed(value, step, "rows")).shuffle(order)
    blocks = []
    for number, start in enumerate(range(0, rows, BLOCK_ROWS)):
        arms = list(arm_ids)
        random.Random(_seed(value, step, f"block:{number}")).shuffle(arms)
        blocks.append({"rows": order[start:start + BLOCK_ROWS], "arms": arms})
    return blocks


def _paired(base, other, rows):
    """``other`` minus ``base`` over the screen rows: task-level counts (overall and by historical status) and the
    family-level directions with their exact one-sided sign tests."""
    delta, table = [], {"wins": 0, "losses": 0, "ties": 0, "unknown": 0}
    strata = {name: {"wins": 0, "losses": 0, "ties": 0, "unknown": 0} for name in ("fail", "pass")}
    for row, b, o in zip(rows, base, other):
        if "unknown" in (b, o):
            key = "unknown"
        else:
            key = "wins" if o == "pass" and b == "fail" else "losses" if o == "fail" and b == "pass" else "ties"
            delta.append((row["family_id"], {"wins": 1, "losses": -1, "ties": 0}[key]))
        table[key] += 1
        strata[row["historical"]][key] += 1
    families = _family_counts(delta)
    return {**table, "jointly_known": table["wins"] + table["losses"] + table["ties"],
            "net_wins": table["wins"] - table["losses"], "by_historical_status": strata,
            **{k: families[k] for k in ("families", "families_improving", "families_regressing", "families_tied",
                                        "family_p_value", "family_harm_p_value")}}


def select(arms, statuses, rows, alpha):
    """The frozen rule ``screen-selection-v2``. Coverage is required of every PAIRED comparison (jointly known rows
    of a variant and a control), not of each arm alone: two arms with 90% known rows each can share far fewer, and
    ranking arms on different observed subsets would reward missingness. Returns (selection, per-arm summaries, the
    A/A table)."""
    needed = min_known(len(rows))
    known = {arm["id"]: sum(s != "unknown" for s in statuses[arm["id"]]) for arm in arms if arm["disposition"] == "scored"}
    replicate = _paired(statuses[CONTROLS[0]], statuses[CONTROLS[1]], rows)
    if min(known[c] for c in CONTROLS) < needed or replicate["jointly_known"] < needed:
        raise LearningPending("screen_control_coverage")
    summaries, eligible = [], []
    for arm in arms:
        if arm["kind"] == "parent" or arm["disposition"] != "scored":
            continue
        mine = statuses[arm["id"]]
        against = {control: _paired(statuses[control], mine, rows) for control in CONTROLS}
        covered = all(t["jointly_known"] >= needed for t in against.values())
        ok = covered and all(t["net_wins"] > 0 and t["family_p_value"] <= alpha for t in against.values())
        score = sum(t["net_wins"] for t in against.values())
        summaries.append({"id": arm["id"], "kind": arm["kind"], "dropped_edit": arm["dropped_edit"],
                          "pass": mine.count("pass"), "fail": mine.count("fail"), "unknown": mine.count("unknown"),
                          "covered": covered, "against": against, "score": score, "eligible": ok})
        if ok:
            eligible.append((-score, arm["skill_bytes"], arm["skill_hash"], arm["id"]))
    if eligible:
        chosen = sorted(eligible)[0][3]
        selection = {"id": chosen, "abstained": False, "reason": "largest_net_against_both_controls_among_eligible"}
    else:
        selection = {"id": "parent", "abstained": True, "reason": "no_eligible_variant"}
    return selection, summaries, replicate


_TAG = re.compile(r"</?[A-Za-z][^<>]{0,40}>")


def _fold(text):
    """Lower-cased alphanumeric words of a text; markup tags such as ``<answer>`` are not content."""
    return " ".join("".join(c.lower() if c.isalnum() else " " for c in _TAG.sub(" ", text)).split())


def text_audit(parent, proposal, pairs):
    """Outcome-blind HEURISTIC audit of what the native selection adds to the parent: how many step-row outputs (their
    folded text, at least 6 characters) the added text quotes. A hit does not prove memorization and a clean count
    does not exclude it; the audit is sealed in the inventory before any arm is scored and never decides anything."""
    added = _fold("\n".join(str(edit.get("content") or "") for edit in proposal["selected"]["edits"]))
    outputs = sorted({_fold(p["row"]["output"]["output"]) for p in pairs} - {""})
    quoted = [o for o in outputs if 6 <= len(o) <= 80 and f" {o} " in f" {added} "]
    return {"kind": "heuristic_outcome_blind_text_audit", "added_chars": len(added), "step_outputs_checked": len(outputs),
            "step_outputs_quoted_in_added_text": len(quoted), "quoted_output_hashes": [digest(o) for o in quoted[:20]],
            "decides_nothing": True}


def run_screen(adapter, ledger, value, root, step, parent, proposal, pairs, *, protected_calls=0, protected_metric=0):
    """Measure the exact variants of one step's native candidate on the step rows and select one text (or abstain).
    ``protected_*`` is the capacity reserved for the post-update challenge; the screen never spends into it. Returns
    the sealed outcome record plus ``selected_skill`` (None on abstention)."""
    require(proposal["status"] == "candidate_ready", "The screen needs a ready native candidate")
    limits = value["active_evidence"]["limits"]
    alpha = limits["screen_alpha_permille"] / 1000
    folder = root / "screen" / str(step)
    arms = build_arms(parent, proposal, skill_budget(value))
    for arm in arms:
        if arm["disposition"] == "scored":
            check_skill(arm["skill"], skill_budget(value))
    rows = [{"task_hash": digest(p["item"]["task"]), "task_id": p["item"]["task"]["task_id"],
             "family_id": p["item"]["task"]["family_id"], "historical": p["host_status"],
             "step_evidence_hash": p["token"]} for p in pairs]
    scored = [arm for arm in arms if arm["disposition"] == "scored"]
    blocks = _schedule(value, step, len(rows), [arm["id"] for arm in scored])
    inventory = seal({"protocol": PROTOCOL, "screen_version": SCREEN_VERSION, "manifest_hash": value["record_hash"],
                      "step": step, "native_proposal_hash": proposal["record_hash"], "parent_hash": digest(parent),
                      "rows": rows, "arms": [{**arm, "rollout": screen_rollout(step, arm["arm"])} for arm in arms],
                      "schedule": {"block_rows": BLOCK_ROWS, "blocks": blocks, "interleaved": True},
                      "selection_rule": SELECTION_RULE, "alpha": alpha, "min_known": min_known(len(rows)),
                      "text_audit": text_audit(parent, proposal, pairs),
                      "expected_metric_positions": len(scored) * len(rows), "note": NOTE})
    outcome_path = folder / "outcome.json"
    if outcome_path.exists():
        outcome = read_json(outcome_path, sealed=True)
        require(outcome["inventory_hash"] == inventory["record_hash"], "Screen replay changed")
        if outcome["status"] != "completed":
            raise LearningPending("screen_control_coverage")
    else:
        if (folder / "inventory.json").exists():
            raise LearningPending("interrupted_screen_no_automatic_resume")
        budget = value["budget"]
        positions = inventory["expected_metric_positions"]
        intents = len(list((ledger.root / "evaluation_intents").glob("*.json")))
        if (intents + positions + protected_metric > budget["max_metric_calls"]
                or ledger.snapshot()["logical_calls"] + 2 * positions + protected_calls > budget["max_api_calls"]):
            raise BudgetExhausted("screen_budget_reserve_unavailable")
        write_json(folder / "inventory.json", inventory)
        items = [p["item"] for p in pairs]
        texts = {arm["id"]: arm for arm in scored}
        cells = {arm["id"]: [None] * len(rows) for arm in scored}
        for block in blocks:
            batch = [items[i] for i in block["rows"]]
            for arm_id in block["arms"]:
                arm = texts[arm_id]
                result = adapter.evaluate_rows(batch, {"skill": arm["skill"]}, rollout=screen_rollout(step, arm["arm"]))
                for index, row in zip(block["rows"], result):
                    cells[arm_id][index] = {"evidence_hash": row["output"]["evidence_hash"], "status": _status(row)}
        statuses = {arm_id: [cell["status"] for cell in column] for arm_id, column in cells.items()}
        measured = {"protocol": PROTOCOL, "screen_version": SCREEN_VERSION, "manifest_hash": value["record_hash"],
                    "step": step, "inventory_hash": inventory["record_hash"],
                    "positions": [{"task_hash": row["task_hash"], "family_id": row["family_id"],
                                   "historical": row["historical"],
                                   "arms": {arm_id: cells[arm_id][index] for arm_id in cells}}
                                  for index, row in enumerate(rows)],
                    "controls": {name: {"pass": statuses[name].count("pass"), "fail": statuses[name].count("fail"),
                                        "unknown": statuses[name].count("unknown")} for name in CONTROLS},
                    "learning_process_data": True, "note": NOTE}
        try:
            selection, summaries, replicate = select(arms, statuses, rows, alpha)
        except LearningPending:
            # the screen was spent but a control lacks coverage: the measurements stay on record, nothing is selected
            write_json(outcome_path, seal({**measured, "status": "control_coverage_insufficient"}))
            raise
        outcome = seal({**measured, "status": "completed",
                        "parent_b_minus_parent_a": replicate, "variants": summaries,
                        "selection": {**selection, "rule": SELECTION_RULE, "alpha": alpha}})
        write_json(outcome_path, outcome)
    chosen = outcome["selection"]["id"]
    skill = None if outcome["selection"]["abstained"] else next(a["skill"] for a in arms if a["id"] == chosen)
    return {"record": outcome, "inventory_hash": inventory["record_hash"], "selected_skill": skill,
            "arms": [{k: arm[k] for k in ("id", "kind", "dropped_edit", "skill_hash", "skill_bytes", "disposition",
                                          "alias_of")} for arm in arms]}


def chain_summary(screen):
    """The count-only projection of a screen for the evidence chain."""
    if screen is None:
        return None
    record = screen["record"]
    return {"version": SCREEN_VERSION, "outcome_hash": record["record_hash"], "inventory_hash": screen["inventory_hash"],
            "rows": len(record["positions"]), "arms": screen["arms"], "controls": record["controls"],
            "parent_b_minus_parent_a": {k: record["parent_b_minus_parent_a"][k]
                                        for k in ("wins", "losses", "ties", "unknown", "net_wins", "family_p_value")},
            "variants": [{"id": v["id"], "kind": v["kind"], "dropped_edit": v["dropped_edit"], "pass": v["pass"],
                          "fail": v["fail"], "unknown": v["unknown"], "eligible": v["eligible"], "score": v["score"],
                          "against": {c: {k: t[k] for k in ("wins", "losses", "ties", "unknown", "net_wins",
                                                            "family_p_value")} for c, t in v["against"].items()}}
                         for v in record["variants"]],
            "selection": record["selection"], "note": NOTE}
