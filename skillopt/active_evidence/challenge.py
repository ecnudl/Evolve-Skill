"""Post-update challenge: the frozen Current and the frozen Candidate re-solve the SAME tasks under the same
environment, tools, budget and fresh rollout keys.

Three sets with separate denominators (never pooled into one generalization claim):
  fresh     -- real development tasks from the challenge pool, drawn after the candidate is frozen by a rule seeded
               by the protocol identity and the step only (tasks drawn by an earlier step are excluded); never
               shown to the diagnoser or the analysts;
  replay    -- a sample of step rows the Current passed (regression check);
  local_fix -- a sample of step rows the Current failed (analyst-seen repair; listed separately, not transfer).
Both Skills are re-run on every position: a historical pass decides membership only, never serves as the
comparison baseline (an identical Skill run twice flips 6-10% of positions). The draw is validated against the
sealed manifest and this step's own evaluations before anything runs. Learning-process data, never a final
evaluation.

Optional fourth set (the optional limit ``train_panel_rows``; a measurement, never a decision input):
  train_panel -- an OUTCOME-BLIND seeded sample of the step's whole task roster (rows whose step evaluation was
               unknown included), balanced over the step families and drawn independently of replay and local_fix,
               whose membership it never changes. A panel position that is also a replay or local-fix position
               reuses that position's evaluations (every task is solved once per Skill); the others are solved in
               their own balanced order. The analysts saw the known rows: the paired result is an in-sample reading,
               recorded next to the fresh one to measure how far a decision made on training rows alone would agree
               with the reserved-pool decision. ``fresh_size_matched`` is the same summary on the first n positions
               of the sealed fresh draw order (n = panel positions): a sensitivity reading at equal panel size."""
from __future__ import annotations

import random

from skillopt.coevolution_v5.core import seal, verify
from skillopt.continual_eval.core import read_json, require, write_json
from skillopt.continual_learning.ledger import BudgetExhausted
from skillopt.continual_learning.skillopt import sign_test_p
from skillopt.validator_pilot.api import digest

from . import PROTOCOL
from .protocol import sampling_identity

SETS = ("fresh", "replay", "local_fix")
TRAIN_PANEL = "train_panel"  # the optional in-sample measurement set; never among the decision's sets
TRAIN_PANEL_RULE = "outcome_blind_stratified_round_robin_over_step_families_of_the_whole_step_roster_v1"
SIZE_MATCHED = "fresh_size_matched"
ROLLOUT_BASE = 1000  # challenge rollout keys never collide with step rollouts (0..99, protocol cap)
DRAW_RULE = "stratified_round_robin_over_challenge_families_seeded_by_manifest_and_step_excluding_earlier_draws_v1"
EXECUTION_ORDER = "balanced_abba_v1"  # per set: seeded halves; half A parent then candidate, half B the reverse
REFERENCE_SLOT = 3  # reference rollout keys: base + 10 * step + 3 + index (index 0 = the parent), at most 7 per step
REFERENCE_ORDER_NOTE = ("the comparator and treatment batches run first, then each reference Skill in order (the parent "
                        "first), consecutively under one model-service identity; batches are not interleaved, so "
                        "service drift between batches is not excluded")
NOISE_NOTE = ("an identical Skill run twice flips 6-10% of positions (recovery.py, v9 note); a small challenge gives "
              "directional evidence only")


def rollouts(step):
    return {"current": ROLLOUT_BASE + 10 * step, "candidate": ROLLOUT_BASE + 10 * step + 1,
            "revision": ROLLOUT_BASE + 10 * step + 2}


def _seed(value, step, name):
    # the sampling identity is the manifest hash itself unless the manifest carries optional limits (protocol.py)
    return int(digest({"manifest_hash": sampling_identity(value), "step": step, "draw": name})[:16], 16)


def _entry(task, seen):
    return {"task_hash": digest(task), "task_id": task["task_id"], "family_id": task["family_id"],
            "family_seen_in_step": task["family_id"] in seen}


def train_panel_entries(value, panel, step, status_of):
    """The deterministic train panel of one step: stratified round-robin over the step families of the WHOLE step
    roster (outcome-blind: whatever each row's step evaluation was, unknown rows included), seeded by the sampling
    identity and the step. ``status_of(task) -> (status, evidence hash or None)`` only annotates the chosen entries;
    it never influences which tasks are chosen."""
    extension = value["active_evidence"]
    wanted, seen = extension["limits"]["train_panel_rows"], set(extension["step_families"])
    roster = {}
    for task in sorted(panel["tasks"], key=lambda t: t["task_id"]):
        if task["family_id"] in seen:
            roster.setdefault(task["family_id"], []).append(task)
    rng = random.Random(_seed(value, step, TRAIN_PANEL))
    order = sorted(roster)
    rng.shuffle(order)
    for family in order:
        rng.shuffle(roster[family])
    chosen = []
    while len(chosen) < wanted and any(roster.values()):
        for family in order:
            if roster[family] and len(chosen) < wanted:
                chosen.append(roster[family].pop())
    entries = []
    for task in chosen:
        status, evidence = status_of(task)
        entries.append({**_entry(task, seen), "step_evidence_hash": evidence, "step_status": status})
    return entries


def draw(value, panel, step, *, step_rows, candidate_hash, root, exclude=()):
    """The sealed draw of one step: written only once a candidate exists, before any candidate evaluation."""
    path = root / "challenge" / str(step) / "draw.json"
    if path.exists():
        record = read_json(path, sealed=True)
        require(record["manifest_hash"] == value["record_hash"] and record["step"] == step
                and record["candidate_hash"] == candidate_hash, "Challenge draw replay changed")
        return record
    extension = value["active_evidence"]
    limits, seen = extension["limits"], set(extension["step_families"])
    pool, excluded = set(extension["challenge_families"]), set(exclude)
    by_family = {}
    for task in sorted(panel["tasks"], key=lambda t: t["task_id"]):
        if task["family_id"] in pool and digest(task) not in excluded:
            by_family.setdefault(task["family_id"], []).append(task)
    rng = random.Random(_seed(value, step, "fresh"))
    families = sorted(by_family)
    rng.shuffle(families)
    for family in families:
        rng.shuffle(by_family[family])
    fresh = []
    while len(fresh) < limits["fresh_tasks"] and any(by_family.values()):
        for family in families:
            if by_family[family] and len(fresh) < limits["fresh_tasks"]:
                fresh.append(_entry(by_family[family].pop(), seen))
    passed = sorted((r for r in step_rows if r["row"]["score"] == 1), key=lambda r: r["token"])
    failed = sorted((r for r in step_rows if r["row"]["score"] == 0), key=lambda r: r["token"])
    replay = random.Random(_seed(value, step, "replay")).sample(passed, min(limits["replay_rows"], len(passed)))
    local = random.Random(_seed(value, step, "local_fix")).sample(failed, min(limits["local_fix_rows"], len(failed)))
    panel_record = {}
    if limits.get("train_panel_rows"):
        known = {digest(r["item"]["task"]): r for r in step_rows}

        def status_of(task):
            row = known.get(digest(task))
            if row is None:
                return "unknown", None
            return ("pass" if row["row"]["score"] == 1 else "fail"), row["token"]

        panel_record = {TRAIN_PANEL: train_panel_entries(value, panel, step, status_of),
                        "train_panel_rule": TRAIN_PANEL_RULE}
    record = seal({"protocol": PROTOCOL, "manifest_hash": value["record_hash"], "step": step,
                   "candidate_hash": candidate_hash, "frozen_before_candidate_evaluation": True, "rule": DRAW_RULE,
                   "rollouts": rollouts(step), "fresh": fresh,
                   "replay": [{**_entry(r["item"]["task"], seen), "step_evidence_hash": r["token"]} for r in replay],
                   "local_fix": [{**_entry(r["item"]["task"], seen), "step_evidence_hash": r["token"]} for r in local],
                   **panel_record,
                   "excluded_earlier_draws": len(excluded),
                   "pool": {"families": len(pool), "tasks": sum(1 for t in panel["tasks"] if t["family_id"] in pool)},
                   "membership_rule": "replay = step rows the Current passed; local_fix = step rows it failed; both "
                                      "Skills are re-run on every position",
                   "learning_process_data": True})
    write_json(path, record)
    return record


def panel_extra(record):
    """Indices of the train-panel entries that are not also a replay or local-fix position (those reuse that
    position's evaluations)."""
    shared = {e["task_hash"] for name in ("replay", "local_fix") for e in record[name]}
    return [i for i, e in enumerate(record.get(TRAIN_PANEL, [])) if e["task_hash"] not in shared]


def required_metric_calls(record):
    return 2 * (sum(len(record[name]) for name in SETS) + len(panel_extra(record)))


def reference_rollout(step, index):
    require(type(index) is int and 0 <= index <= 9 - REFERENCE_SLOT, "Too many reference Skills for one step's keys")
    return ROLLOUT_BASE + 10 * step + REFERENCE_SLOT + index


def _validate_draw(value, panel, step, record, current, candidate, ledger):
    """The draw must be this step's sealed draw of this frozen candidate, every fresh position a challenge-pool task,
    every replay/local-fix position this step's own evaluation of a step task under the Current."""
    verify(record)
    extension = value["active_evidence"]
    require(record["protocol"] == PROTOCOL and record["manifest_hash"] == value["record_hash"]
            and record["step"] == step and record["candidate_hash"] == digest(candidate)
            and record["rollouts"] == rollouts(step) and record["frozen_before_candidate_evaluation"] is True,
            "Draw does not belong to this step's frozen candidate")
    tasks = {digest(t): t for t in panel["tasks"]}
    pool, steps = set(extension["challenge_families"]), set(extension["step_families"])
    hashes = [e["task_hash"] for e in record["fresh"]]
    require(len(set(hashes)) == len(hashes), "Duplicate fresh positions")
    for entry in record["fresh"]:
        task = tasks.get(entry["task_hash"])
        require(task is not None and task["family_id"] == entry["family_id"] and task["family_id"] in pool,
                "A fresh position is not a challenge-pool task")
    for name, status in (("replay", "pass"), ("local_fix", "fail")):
        for entry in record[name]:
            task = tasks.get(entry["task_hash"])
            require(task is not None and task["family_id"] == entry["family_id"] and task["family_id"] in steps,
                    f"A {name} position is not a step task")
            request = {"manifest_hash": value["record_hash"], "candidate_hash": digest({"skill": current}),
                       "task_hash": entry["task_hash"], "role": "train", "repeat": 0, "benchmark": value["benchmark"],
                       "rollout": step}
            saved = read_json(ledger.root / "evaluations" / (digest(request) + ".json"), sealed=True)
            require(saved["record_hash"] == entry["step_evidence_hash"] and saved["score"]["status"] == status,
                    f"A {name} position is not this step's {status}ed evaluation under the Current")
    if not extension["limits"].get("train_panel_rows"):
        require(TRAIN_PANEL not in record and "train_panel_rule" not in record,
                "A train panel was drawn although the sealed limits do not ask for one")
        return

    def status_of(task):
        request = {"manifest_hash": value["record_hash"], "candidate_hash": digest({"skill": current}),
                   "task_hash": digest(task), "role": "train", "repeat": 0, "benchmark": value["benchmark"],
                   "rollout": step}
        saved = read_json(ledger.root / "evaluations" / (digest(request) + ".json"), sealed=True)
        status = saved["score"]["status"]
        require(status in ("pass", "fail", "unknown"), "A step evaluation carries no usable status")
        return status, (saved["record_hash"] if status != "unknown" else None)

    # the panel is rebuilt from the sealed manifest, the panel file and this step's own sealed evaluations and must
    # be exactly the recorded one: entries, order, count and annotations (no truncated or hand-picked panel)
    require(record.get("train_panel_rule") == TRAIN_PANEL_RULE
            and record.get(TRAIN_PANEL) == train_panel_entries(value, panel, step, status_of),
            "The train panel is not this step's deterministic outcome-blind draw")


def _status(row):
    return "unknown" if row["score"] is None else ("pass" if row["score"] == 1 else "fail")


def _pair(current, candidate):
    if current is None and candidate is None:
        return "both_unknown"
    if candidate is None:
        return "candidate_unknown"
    if current is None:
        return "current_unknown"
    return "win" if candidate > current else "loss" if candidate < current else "tie"


def _counts(positions):
    counts = {k: 0 for k in ("win", "loss", "tie", "candidate_unknown", "current_unknown", "both_unknown")}
    for position in positions:
        counts[position["pair"]] += 1
    return counts


UNKNOWN_PAIRS = ("candidate_unknown", "current_unknown", "both_unknown")


def _family_counts(deltas):
    """Family directions from (family_id, delta) pairs: a family's net is the sum of its positions' deltas."""
    families = {}
    for family, delta in deltas:
        families[family] = families.get(family, 0) + delta
    improving = sum(v > 0 for v in families.values())
    regressing = sum(v < 0 for v in families.values())
    return {"families": len(families), "families_improving": improving, "families_regressing": regressing,
            "families_tied": len(families) - improving - regressing, "families_non_tied": improving + regressing,
            # exact ONE-sided sign tests on the non-tied families (gain: improving; harm: regressing)
            "family_p_value": sign_test_p(improving, regressing),
            "family_harm_p_value": sign_test_p(regressing, improving)}


def _summary(positions):
    """Paired summary of one set. The decision's unit of evidence is the FAMILY (net of its jointly known positions);
    ``adverse`` recomputes the family directions and the task-level net with every position that has an unknown side
    counted as a candidate loss (a sensitivity bound, never an imputation of the recorded outcome)."""
    counts = _counts(positions)
    delta = {"win": 1, "loss": -1, "tie": 0}
    known = _family_counts([(p["family_id"], delta[p["pair"]]) for p in positions if p["pair"] in delta])
    adverse = _family_counts([(p["family_id"], delta.get(p["pair"], -1)) for p in positions])
    unknown = sum(counts[k] for k in UNKNOWN_PAIRS)
    jointly = counts["win"] + counts["loss"] + counts["tie"]
    strata = {}
    for name, flag in (("seen_family", True), ("unseen_family", False)):
        subset = _counts([p for p in positions if p["family_seen_in_step"] is flag])
        strata[name] = {"positions": sum(subset.values()), "wins": subset["win"], "losses": subset["loss"]}
    return {"positions": len(positions), "wins": counts["win"], "losses": counts["loss"], "ties": counts["tie"],
            "candidate_unknown": counts["candidate_unknown"], "current_unknown": counts["current_unknown"],
            "both_unknown": counts["both_unknown"], "jointly_known": jointly, "net_wins": counts["win"] - counts["loss"],
            **known, "strata": strata,
            "adverse": {"rule": "every position with an unknown side counted as a candidate loss",
                        "unknown_positions": unknown, "net_wins": counts["win"] - counts["loss"] - unknown,
                        **{k: adverse[k] for k in ("families_improving", "families_regressing", "family_p_value")}},
            # replay: a loss is a regression of a position the Current passed historically (both re-run here);
            # local_fix: a win is a repaired analyst-seen failure
            "regressions": counts["loss"], "fixed": counts["win"]}


def balanced_halves(value, step, name, count):
    """The frozen execution order of one set: a seeded split of its positions into half A (parent first) and half B
    (candidate first); with an odd count half A has the extra position."""
    order = list(range(count))
    random.Random(_seed(value, step, "order:" + name)).shuffle(order)
    cut = (count + 1) // 2
    return sorted(order[:cut]), sorted(order[cut:])


def run(adapter, ledger, value, panel, step, record, current, candidate, root):
    """Solve every drawn position with both frozen Skills (fresh rollout keys, balanced order) and seal the paired
    outcome. A missing budget reserve is an infrastructure stop (BudgetExhausted -> pending), never a decision input;
    a draw without any fresh position is an honest ``not_run`` outcome -- nothing is evaluated, replay rows alone
    never decide, and the decision parks the candidate."""
    path = root / "challenge" / str(step) / "outcome.json"
    if path.exists():
        outcome = read_json(path, sealed=True)
        require(outcome["draw_hash"] == record["record_hash"] and outcome["candidate_hash"] == digest(candidate)
                and outcome["current_hash"] == digest(current), "Challenge outcome replay changed")
        return outcome
    _validate_draw(value, panel, step, record, current, candidate, ledger)
    binding = {"protocol": PROTOCOL, "manifest_hash": value["record_hash"], "step": step,
               "draw_hash": record["record_hash"], "candidate_hash": digest(candidate), "current_hash": digest(current),
               "rollouts": record["rollouts"], "learning_process_data": True, "same_skill_noise": NOISE_NOTE}
    needed = required_metric_calls(record)
    if not record["fresh"]:
        # no eligible fresh task (an exhausted pool): nothing is evaluated -- replay and local-fix rows alone can
        # neither keep nor revert a candidate; the decision parks it as insufficient evidence
        outcome = seal({**binding, "status": "not_run", "reason": "no_eligible_fresh_tasks", "required_metric_calls": 0,
                        "drawn": {name: len(record[name]) for name in SETS}})
        write_json(path, outcome)
        return outcome
    budget = value["budget"]
    intents = len(list((ledger.root / "evaluation_intents").glob("*.json")))
    if intents + needed > budget["max_metric_calls"] or ledger.snapshot()["logical_calls"] + 2 * needed > budget["max_api_calls"]:
        raise BudgetExhausted("challenge_budget_reserve_unavailable")
    tasks = {digest(t): t for t in panel["tasks"]}
    skills = {"current": current, "candidate": candidate}
    positions, halves = [], {}
    for name in SETS:
        entries = record[name]
        if not entries:
            continue
        items = [{"role": "train", "task": tasks[e["task_hash"]]} for e in entries]
        rows = {key: [None] * len(entries) for key in skills}
        first, second = balanced_halves(value, step, name, len(entries))
        halves[name] = {"parent_first": first, "candidate_first": second}
        # balanced order: half A parent then candidate, half B candidate then parent (drift between batches is
        # counterbalanced, not assumed away); each Skill keeps its own rollout key
        for members, sequence in ((first, ("current", "candidate")), (second, ("candidate", "current"))):
            if not members:
                continue
            batch = [items[i] for i in members]
            for key in sequence:
                result = adapter.evaluate_rows(batch, {"skill": skills[key]}, rollout=record["rollouts"][key])
                for index, row in zip(members, result):
                    rows[key][index] = row
        for index, entry in enumerate(entries):
            cur, cand = rows["current"][index], rows["candidate"][index]
            positions.append({"set": name, **entry,
                              "current": {"evidence_hash": cur["output"]["evidence_hash"], "status": _status(cur)},
                              "candidate": {"evidence_hash": cand["output"]["evidence_hash"], "status": _status(cand)},
                              "pair": _pair(cur["score"], cand["score"])})
    summary = {name: _summary([p for p in positions if p["set"] == name]) for name in SETS}
    if TRAIN_PANEL in record:
        entries = record[TRAIN_PANEL]
        shared = {p["task_hash"]: p for p in positions if p["set"] in ("replay", "local_fix")}
        extra = panel_extra(record)
        rows = {key: {} for key in skills}
        first, second = balanced_halves(value, step, TRAIN_PANEL, len(extra))
        halves[TRAIN_PANEL] = {"parent_first": [extra[i] for i in first], "candidate_first": [extra[i] for i in second],
                               "reused_positions": len(entries) - len(extra)}
        for members, sequence in ((first, ("current", "candidate")), (second, ("candidate", "current"))):
            if not members:
                continue
            batch = [{"role": "train", "task": tasks[entries[extra[i]]["task_hash"]]} for i in members]
            for key in sequence:
                result = adapter.evaluate_rows(batch, {"skill": skills[key]}, rollout=record["rollouts"][key])
                for i, row in zip(members, result):
                    rows[key][extra[i]] = row
        panel_positions = []
        for index, entry in enumerate(entries):
            if index in rows["current"]:
                cur, cand = rows["current"][index], rows["candidate"][index]
                sides = {"current": {"evidence_hash": cur["output"]["evidence_hash"], "status": _status(cur)},
                         "candidate": {"evidence_hash": cand["output"]["evidence_hash"], "status": _status(cand)},
                         "pair": _pair(cur["score"], cand["score"]), "shared_with": None}
            else:  # the same task under the same rollout keys: that position's evaluations, never a second solve
                source = shared[entry["task_hash"]]
                sides = {"current": source["current"], "candidate": source["candidate"], "pair": source["pair"],
                         "shared_with": source["set"]}
            panel_positions.append({"set": TRAIN_PANEL, **entry, **sides})
        positions.extend(panel_positions)
        by_status = {}
        for status in ("pass", "fail", "unknown"):
            subset = _counts([p for p in panel_positions if p["step_status"] == status])
            by_status["step_" + status] = {"positions": sum(subset.values()), "wins": subset["win"],
                                           "losses": subset["loss"], "ties": subset["tie"]}
        # in-sample: the analysts saw the known rows; a measurement next to the fresh panel, never a decision input
        summary[TRAIN_PANEL] = {**_summary(panel_positions), "by_step_status": by_status,
                                "reused_positions": len(entries) - len(extra), "in_sample": True,
                                "decision_input": False}
        fresh_positions = [p for p in positions if p["set"] == "fresh"]
        matched_rule = "the first n positions of the sealed fresh draw order, n = train-panel positions"
        if len(fresh_positions) < len(entries):
            # fewer fresh positions than panel positions: no equal-size reading exists (never a smaller one in disguise)
            summary[SIZE_MATCHED] = {"positions": len(fresh_positions), "wanted_positions": len(entries),
                                     "unavailable": "fewer_fresh_positions_than_train_panel_positions",
                                     "sensitivity_only": True, "rule": matched_rule, "decision_input": False}
        else:
            summary[SIZE_MATCHED] = {**_summary(fresh_positions[:len(entries)]), "sensitivity_only": True,
                                     "rule": matched_rule, "decision_input": False}
    outcome = seal({**binding, "status": "completed", "positions": positions, "summary": summary,
                    "execution_order": {"version": EXECUTION_ORDER, "halves": halves}})
    write_json(path, outcome)
    return outcome


def _reference_pair(reference, branch):
    """Branch minus reference on one position, from the two sealed statuses."""
    if "unknown" in (reference, branch):
        return "unknown"
    return "win" if branch == "pass" and reference == "fail" else "loss" if branch == "fail" and reference == "pass" else "tie"


def _reference_counts(pairs):
    counts = {name: sum(p == name for p in pairs) for name in ("win", "loss", "tie", "unknown")}
    return {"positions": len(pairs), "wins": counts["win"], "losses": counts["loss"], "ties": counts["tie"],
            "unknown": counts["unknown"], "jointly_known": counts["win"] + counts["loss"] + counts["tie"]}


def run_references(adapter, ledger, value, panel, step, record, outcome, references, root):
    """Matched-branch study only: each reference Skill (the parent first) solves the drawn fresh positions once under
    its own rollout key, after both branches; sealed with the paired counts of each branch against each reference.
    ``references`` is an ordered list of (name, skill). Evaluation only: nothing here selects or deploys anything."""
    path = root / "challenge" / str(step) / "references.json"
    listing = [{"name": name, "skill_hash": digest(skill), "request_candidate_hash": digest({"skill": skill}),
                "rollout": reference_rollout(step, index)} for index, (name, skill) in enumerate(references)]
    binding = {"protocol": PROTOCOL, "manifest_hash": value["record_hash"], "step": step,
               "draw_hash": record["record_hash"], "outcome_hash": outcome["record_hash"], "references": listing,
               "learning_process_data": True, "evaluation_only": True, "order_note": REFERENCE_ORDER_NOTE,
               "same_skill_noise": NOISE_NOTE}
    if path.exists():
        saved = read_json(path, sealed=True)
        require(all(saved[k] == v for k, v in binding.items()), "Reference evaluation replay changed")
        return saved
    require(len({name for name, _ in references}) == len(references) and references and references[0][0] == "parent",
            "Reference Skills are uniquely named and start with the parent")
    fresh = [p for p in outcome.get("positions", []) if p["set"] == "fresh"] if outcome["status"] == "completed" else []
    if not fresh:
        saved = seal({**binding, "status": "not_run", "reason": "no_holdout_positions"})
        write_json(path, saved)
        return saved
    require([p["task_hash"] for p in fresh] == [e["task_hash"] for e in record["fresh"]],
            "The paired outcome does not cover the drawn holdout in order")
    needed = len(references) * len(fresh)
    budget = value["budget"]
    intents = len(list((ledger.root / "evaluation_intents").glob("*.json")))
    if intents + needed > budget["max_metric_calls"] or ledger.snapshot()["logical_calls"] + 2 * needed > budget["max_api_calls"]:
        raise BudgetExhausted("challenge_budget_reserve_unavailable")
    tasks = {digest(t): t for t in panel["tasks"]}
    items = [{"role": "train", "task": tasks[p["task_hash"]]} for p in fresh]
    positions = [{"task_hash": p["task_hash"], "task_id": p["task_id"], "family_id": p["family_id"], "reference": {}}
                 for p in fresh]
    summary, parent_statuses = {}, None
    for entry, (name, skill) in zip(listing, references):
        rows = adapter.evaluate_rows(items, {"skill": skill}, rollout=entry["rollout"])
        statuses = [_status(row) for row in rows]
        for position, row, status in zip(positions, rows, statuses):
            position["reference"][name] = {"evidence_hash": row["output"]["evidence_hash"], "status": status}
        summary[name] = {
            "pass": statuses.count("pass"), "fail": statuses.count("fail"), "unknown": statuses.count("unknown"),
            # wins = the branch passes a position this reference fails
            "comparator_minus_reference": _reference_counts(
                [_reference_pair(s, p["current"]["status"]) for s, p in zip(statuses, fresh)]),
            "treatment_minus_reference": _reference_counts(
                [_reference_pair(s, p["candidate"]["status"]) for s, p in zip(statuses, fresh)])}
        if parent_statuses is None:
            parent_statuses = statuses  # the parent is evaluated first
        else:
            # the instrument check: a named reference against the parent on the same positions (wins = the reference
            # passes a position the parent fails)
            summary[name]["reference_minus_parent"] = _reference_counts(
                [_reference_pair(p, s) for p, s in zip(parent_statuses, statuses)])
    saved = seal({**binding, "status": "completed", "positions": positions, "summary": summary,
                  "branch_pass": {"comparator": sum(p["current"]["status"] == "pass" for p in fresh),
                                  "treatment": sum(p["candidate"]["status"] == "pass" for p in fresh)}})
    write_json(path, saved)
    return saved
