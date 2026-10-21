"""Verification-note binding study (``fivebench-rubric-binding-study-v1``; 2026-10-15 04:20, written before any
result; the follow-up of the rubric-form study). The rubric-form series on OfficeQA (six blocks) found no difference
between rubric forms and no supported granularity, and a zero-call reading of the sealed proposals showed why: the
analysts add nearly the same sections whatever verification note they see, and their reasoning rarely refers to a
note. So the question moves from "which rubric" to "does the analyst USE the note" -- the same flow (train execution
-> rubric feedback -> analyst -> candidate -> selection), one more thing varied: the failure analysts' system prompt.

Arms (one fresh train rollout per block shared by all, the rubric-form instrument):

  scalar               pass/fail only (the control)
  default_text         the benchmark's frozen default rubric, judged by the model (learning v10 as it is)
  default_text_bound   the SAME reports and traces as default_text; the failure analysts' system prompt ends with
                       the binding preamble
  global_text          the benchmark-agnostic rubric, judged by the model (the arm that led descriptively)
  global_text_bound    the same reports as global_text + the binding preamble

A bound arm reuses its base arm's judgments, calibration and sealed reports (no extra judge call): the only
difference is the preamble on the failure minibatches (``BINDING``: every failed check named in a note must be
answered by an edit placed first, or by a stated reason). In a block whose base rubric is not authorized there are
no notes: the bound arm then gets exactly its base arm's prompt and feedback (binding not applied, recorded), and
the pair differs by proposal sampling only. Updater, parser, retries, selection set and evaluation are the
rubric-form study's (``rubric_form.propose_arm`` with ``analyst_binding``).

Reading (pre-registered in ANALYSIS): the primary contrasts are bound - base per rubric, by exact block sign-flip
over the blocks where the binding was applied (informative blocks); alpha 0.05 two-sided, so six informative blocks
of one sign are needed; the other contrasts and all per-position counts are descriptive. The rubric-form study's
claim limits apply unchanged: a candidate scored higher on the selection set is not an accepted Skill.
"""
from __future__ import annotations

import random
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

from skillopt.coevolution_v5.core import seal, verify
from skillopt.continual_eval import backends
from skillopt.continual_eval.core import output_lock, read_json, require, safe_path, write_json
from skillopt.continual_learning.gepa import Adapter
from skillopt.continual_learning.ledger import LearningPending, Ledger
from skillopt.continual_learning.recovery import POLICY_V10, client_options
from skillopt.continual_learning.skillopt import native_sources
from skillopt.validator_pilot.api import CachedAPI, digest

from . import rubric_form as rf
from .common import bind_rows, run_cells, study_manifest, study_sources, validate_rubric_record
from .fixed_rubric import arm_metrics, sign_flip_two_sided
from .matched_feedback import _counts

PROTOCOL = "fivebench-rubric-binding-study-v1"
BENCHMARKS = rf.BENCHMARKS
ARMS = ("scalar", "default_text", "default_text_bound", "global_text", "global_text_bound")
TEXT_ARMS = ("default_text", "global_text")  # judged once per block; a bound arm reuses its base arm's records
BOUND = {"default_text_bound": "default_text", "global_text_bound": "global_text"}
SLOTS = ("parent", *ARMS)
MODULES = ("__init__.py", "common.py", "fixed_rubric.py", "matched_feedback.py", "rubric_form.py", "rubric_binding.py")
PLAN_SEED = rf.PLAN_SEED
EDIT_BUDGET = rf.EDIT_BUDGET
BINDING = {
    "version": "verification-note-binding-v1",
    "preamble": (
        "\n\nVERIFICATION NOTES ARE BINDING. Some failed rows end with a verifier note that names specific checks "
        "which FAILED on that output. Treat every failed check as the primary finding for its row. Before anything "
        "else, write the edit that would have made that output pass that check -- a reusable rule or procedure in "
        "the skill's own terms, never the row's values, quotes or entities -- and place these edits FIRST in "
        "`edits`, one per distinct failed check. If an existing skill rule already covers a failed check, say which "
        "rule in `reasoning` instead of adding a duplicate. Stay within the edit budget L you are given: when more "
        "distinct failed checks remain than L allows, merge checks of one kind into one rule and give priority to the "
        "checks that failed on the most rows; name in `reasoning` every failed check that received no edit and why. "
        "Only after every failed check is answered may you add edits motivated by your own reading of the failures. "
        "A passed check is not a problem to fix."
    ),
}
ANALYSIS = {
    "unit": rf.ANALYSIS["unit"],
    "confirmatory": {"test": "exact_block_sign_flip_two_sided_on_pass_count_differences", "alpha": 0.05,
                     "informative_blocks": "a bound-minus-base contrast counts the blocks where the binding was applied "
                                           "(base rubric authorized); every other contrast counts all blocks",
                     "note": "with fewer than six informative blocks no contrast can reach alpha; it is then descriptive"},
    "descriptive": rf.ANALYSIS["descriptive"],
    "primary": [["global_text_bound", "global_text"], ["default_text_bound", "default_text"]],
    "lead": ["global_text_bound", "global_text"],
    "multiplicity": "each primary contrast is tested on its own at alpha 0.05, without correction; 'binding supported' "
                    "means the LEAD contrast (the global rubric, authorized in every OfficeQA block so far) is "
                    "supported; the default-rubric pair is a within-dataset replication reported on its own and makes "
                    "no claim by itself. Only primary contrasts can be 'supported'; every other contrast is descriptive",
    "compliance": "a supported difference says the candidates proposed under the bound PROMPT scored differently on these "
                  "blocks (the test is two-sided: beneficial binding additionally requires direction treatment_higher); "
                  "whether the analysts actually answered the notes is a separate zero-call audit of the raw proposals "
                  "(do the bound arm's first edits name the failed checks), not something the yield difference establishes",
    "contrasts": [["global_text_bound", "global_text"], ["default_text_bound", "default_text"],
                  ["global_text_bound", "scalar"], ["global_text", "scalar"],
                  ["default_text_bound", "scalar"], ["default_text", "scalar"], ["global_text", "default_text"]],
    "verifier_endpoints": "per judged rubric: authorized blocks, pooled detection rate and false-rejection rate on the "
                          "shared rollouts (a bound arm shares its base arm's endpoints)",
    "binding_contrast": "bound vs base compares two analyst SYSTEM PROMPTS on identical traces, reports and sampling "
                        "seeds; the analyst samples are independent draws, so a difference also contains proposal noise",
    "claim_limits": rf.ANALYSIS["claim_limits"],
}


def rubrics(benchmark):
    records = rf.rubrics(benchmark)
    return {arm: records[arm] for arm in TEXT_ARMS}


# ----------------------------------------------------------------------------- protocol
def build_spec(template, benchmark, blocks, source):
    require(type(blocks) is int and 1 <= blocks <= 16, "One to sixteen blocks")
    records = rubrics(benchmark)
    spec = seal({"protocol": PROTOCOL, "benchmark": benchmark, "arms": list(ARMS), "text_arms": list(TEXT_ARMS),
                 "bound_arms": dict(BOUND), "blocks": blocks, "rubrics": records,
                 "rubric_policy_hashes": {arm: records[arm]["policy_hash"] for arm in TEXT_ARMS},
                 "binding": dict(BINDING), "template": template, "budget": dict(rf.BUDGETS[benchmark]),
                 "plan_seed": PLAN_SEED, "edit_budget": EDIT_BUDGET, "analysis": ANALYSIS, "source": source,
                 "information_origin": "fresh_train_rollouts_scalar_host_feedback_and_label_free_rubric_reports",
                 "deployment_authorized": False})
    validate_spec(spec)
    return spec


def validate_spec(spec):
    verify(spec)
    require(spec["protocol"] == PROTOCOL and spec["benchmark"] in BENCHMARKS and spec["arms"] == list(ARMS)
            and spec["text_arms"] == list(TEXT_ARMS) and spec["bound_arms"] == dict(BOUND)
            and type(spec["blocks"]) is int and 1 <= spec["blocks"] <= 16 and spec["budget"] == rf.BUDGETS[spec["benchmark"]]
            and spec["plan_seed"] == PLAN_SEED and spec["edit_budget"] == EDIT_BUDGET and spec["analysis"] == ANALYSIS
            and spec["binding"] == BINDING and spec["rubrics"] == rubrics(spec["benchmark"]),
            "Not this study's registered protocol")
    for arm in TEXT_ARMS:
        validate_rubric_record(spec["rubrics"][arm], spec["benchmark"])
        require(spec["rubric_policy_hashes"][arm] == spec["rubrics"][arm]["policy_hash"], "Rubric hash registry differs")
    template = spec["template"]
    require(set(template) == {"panel_hash", "train_families", "selection_families", "model", "runtime", "parent_skill",
                              "seed", "recovery_policy"}
            and template["recovery_policy"] == POLICY_V10, "The template is not a v10 (v7 delivery) template")
    return spec


def block_plan(spec, block):
    """Every randomized choice of a block from the registered seed, the block index and the series label (one-block
    studies run in series get different plans), as in the rubric-form study."""
    rng = random.Random(digest({"plan_seed": spec["plan_seed"], "protocol": PROTOCOL, "block": block,
                                "series": spec["source"].get("series")}))
    proposal_order, evaluation_order = list(ARMS), list(SLOTS)
    rng.shuffle(proposal_order)
    rng.shuffle(evaluation_order)
    return {"block": block, "train_rollout": block, "minibatch_seed": rng.randrange(2**31),
            "judge_seed": rng.randrange(2**31), "proposal_order": proposal_order, "evaluation_order": evaluation_order,
            "validation_rollouts": {slot: 1 + len(SLOTS) * block + index for index, slot in enumerate(SLOTS)}}


# ----------------------------------------------------------------------------- one block
def run_block(spec, value, root, ledger, adapter, train, selection, block, workers):
    """One block: shared fresh train rollout -> the two judged rubrics' reports and calibration -> one native proposal
    per arm (registered order; a bound arm reuses its base arm's reports and adds the binding preamble when that
    rubric is authorized) -> candidates frozen -> selection passes of the parent and of every distinct candidate."""
    plan = block_plan(spec, block)
    folder = root / "blocks" / str(block)
    write_json(folder / "plan.json", seal({"protocol_hash": spec["record_hash"], **plan}))
    parent, rollout = value["parent_skill"], plan["train_rollout"]
    rows = adapter.evaluate_rows(train[:1], {"skill": parent}, rollout=rollout)  # first reply alone (health barrier)
    rows += adapter.evaluate_rows(train[1:], {"skill": parent}, rollout=rollout)
    pairs, unknown = bind_rows(ledger, value, train, rows, parent, rollout)
    if not pairs:
        raise LearningPending("insufficient_known_train")
    by_token = {row["output"]["evidence_hash"]: (item, row) for item, row in pairs}
    tokens = sorted(by_token)
    traces = [{**row["trajectory"], "evidence_hash": row["output"]["evidence_hash"]} for _, row in pairs]
    cells = [[arm, token] for token in tokens for arm in TEXT_ARMS]
    random.Random(plan["judge_seed"]).shuffle(cells)
    write_json(folder / "schedule.json", seal({"protocol_hash": spec["record_hash"], "block": block,
                                               "eligible_tokens": tokens, "cells": cells}))
    verifiers = {arm: rf.TextRubricVerifier(value, ledger, root, rollout, arm, spec["rubrics"][arm]) for arm in TEXT_ARMS}
    records = run_cells([tuple(cell) for cell in cells], verifiers, by_token, workers)
    summaries, reports = {}, {}
    for arm in TEXT_ARMS:
        summaries[arm], reports[arm] = verifiers[arm].calibrate([records[arm][t] for t in
                                                                 (row["output"]["evidence_hash"] for _, row in pairs)])
    meta = [{"token": row["output"]["evidence_hash"], "family": item["task"]["family_id"],
             "host_status": "fail" if row["score"] == 0 else "pass"} for item, row in pairs]
    proposals, injected, applied, failures = {}, {}, {}, {}
    for arm in plan["proposal_order"]:
        base = BOUND.get(arm, arm)
        arm_traces, kwargs = deepcopy(traces), {}
        authorized = base in TEXT_ARMS and summaries[base]["authorized"]
        if authorized:
            for trace in arm_traces:
                report = reports[base].get(trace["evidence_hash"])
                if (trace["Feedback"]["status"] == "fail" and report is not None and report["authorized"]
                        and report["feedback"] is not None):
                    trace["Feedback"] = {**trace["Feedback"], "verifier": report["feedback"]}
            kwargs = {"verifier_root": verifiers[base].root, "verifier_reports": reports[base],
                      "policy_record": verifiers[base].rubric, "verifier_label": f"{rollout}-{base}"}
            if arm in BOUND:
                kwargs["analyst_binding"] = spec["binding"]
        injected[arm] = sum("verifier" in t["Feedback"] for t in arm_traces)
        applied[arm] = arm in BOUND and authorized
        try:
            proposals[arm] = rf.propose_arm(parent, arm_traces, root / "native" / str(block) / arm, ledger, arm=arm,
                                            label=f"{rollout}-{arm}", rollout=rollout, seed=plan["minibatch_seed"],
                                            minibatch_size=value["budget"]["minibatch_size"], edit_budget=spec["edit_budget"],
                                            study=PROTOCOL, **kwargs)
        except LearningPending as exc:
            tolerated = rf.tolerated_proposal_failure(exc)
            if tolerated is None:
                raise
            failures[arm] = tolerated  # the analyst's reply was rejected: this arm stays on the parent for the block
            proposals[arm] = None
    dispositions = {}
    for arm in ARMS:
        base = BOUND.get(arm, arm)
        common = {"verifier_authorized": summaries[base]["authorized"] if base in TEXT_ARMS else None,
                  "traces_with_feedback": injected[arm], "rubric_guidance": base in TEXT_ARMS and summaries[base]["authorized"],
                  "binding_applied": applied[arm], "base_arm": base if arm in BOUND else None}
        proposal = proposals[arm]
        if proposal is None:
            dispositions[arm] = {"proposal_hash": None, "status": "proposal_failed", "failure": failures[arm],
                                 "candidate_hash": None, "candidate_bytes": None, "rejected_candidate_hash": None,
                                 "evaluated": "parent_fallback", "native_fallbacks": None, **common}
            continue
        changed = proposal["status"] == "candidate_ready"
        dispositions[arm] = {"proposal_hash": proposal["record_hash"], "status": proposal["status"], "failure": None,
                             "candidate_hash": digest(proposal["candidate_skill"]) if changed else None,
                             "candidate_bytes": len(proposal["candidate_skill"].encode()) if changed else None,
                             "rejected_candidate_hash": proposal.get("rejected_candidate_hash"),
                             "evaluated": "candidate" if changed else "parent_fallback",
                             "native_fallbacks": proposal["native_fallbacks"], **common}
    candidates = seal({"protocol_hash": spec["record_hash"], "block": block, "train_rollout": rollout,
                       "train": {"tasks": len(train), "eligible_rows": len(pairs), "unknown_rows": unknown,
                                 "host_fail_rows": sum(m["host_status"] == "fail" for m in meta),
                                 "host_pass_rows": sum(m["host_status"] == "pass" for m in meta)},
                       "verifier": {arm: {"summary_hash": summaries[arm]["record_hash"],
                                          "authorized": summaries[arm]["authorized"],
                                          **{k: summaries[arm][k] for k in ("detections", "host_fail_rows",
                                                                           "false_rejections", "host_pass_rows",
                                                                           "false_rejection_rate", "coverage", "delivery")},
                                          "all_eligible_rows": arm_metrics(meta, records[arm])}
                                    for arm in TEXT_ARMS},
                       "dispositions": dispositions, "frozen_before_validation": True})
    write_json(folder / "candidates.json", candidates)
    evaluations, by_skill = {}, {}  # one evaluation per DISTINCT text per block: an identical candidate shares it
    for slot in plan["evaluation_order"]:
        if slot == "parent":
            skill = parent
        elif dispositions[slot]["evaluated"] == "candidate":
            skill = proposals[slot]["candidate_skill"]
        else:
            continue
        if digest(skill) in by_skill:
            dispositions[slot]["shares_evaluation_of"] = by_skill[digest(skill)]
            continue
        rows = adapter.evaluate_rows(selection, {"skill": skill}, rollout=plan["validation_rollouts"][slot])
        evaluations[slot] = {"skill_hash": digest(skill), "rollout": plan["validation_rollouts"][slot], **_counts(rows),
                             "statuses": ["pass" if r["score"] == 1 else "fail" if r["score"] == 0 else "unknown" for r in rows]}
        by_skill[digest(skill)] = slot
    arms = {}
    for arm in ARMS:
        slot = ("parent" if dispositions[arm]["evaluated"] != "candidate"
                else dispositions[arm].get("shares_evaluation_of", arm))
        arms[arm] = {**evaluations[slot], "evaluated": dispositions[arm]["evaluated"], "evaluation_slot": slot}
    outcome = seal({"protocol_hash": spec["record_hash"], "block": block, "candidates_hash": candidates["record_hash"],
                    "evaluations": evaluations, "arms": arms,
                    "shared_evaluations": {arm: dispositions[arm]["shares_evaluation_of"] for arm in ARMS
                                           if "shares_evaluation_of" in dispositions[arm]}})
    write_json(folder / "outcome.json", outcome)
    return candidates, outcome


# ----------------------------------------------------------------------------- analysis
def analyze(spec, candidates, outcomes):
    def contrast(treatment, control):
        primary = [treatment, control] in spec["analysis"]["primary"]
        kept = [(c, o) for c, o in zip(candidates, outcomes)
                if not primary or c["dispositions"][treatment]["binding_applied"]]
        differences = [o["arms"][treatment]["pass"] - o["arms"][control]["pass"] for _, o in kept]
        everything = [o["arms"][treatment]["pass"] - o["arms"][control]["pass"] for o in outcomes]
        exact = sign_flip_two_sided(differences) if differences else {"observed_sum": 0, "informative_families": 0, "p_value": 1.0}
        wins = losses = 0
        for _, o in kept:
            for a, b in zip(o["arms"][treatment]["statuses"], o["arms"][control]["statuses"]):
                wins += a == "pass" and b == "fail"
                losses += a == "fail" and b == "pass"
        low = [o["arms"][treatment]["pass"] - o["arms"][control]["pass"] - o["arms"][control]["unknown"] for _, o in kept]
        high = [o["arms"][treatment]["pass"] + o["arms"][treatment]["unknown"] - o["arms"][control]["pass"] for _, o in kept]
        positions = sum(o["arms"][control]["positions"] for _, o in kept)
        total = sum(differences)
        return {"treatment": treatment, "control": control, "primary": primary, "differences": differences,
                "all_block_differences": everything, "informative_blocks": len(kept),
                "mean_difference": total / len(differences) if differences else None,
                "pooled_yield_difference": total / positions if positions else None,
                "block_sign_flip": {"observed_sum": exact["observed_sum"], "informative_blocks": exact["informative_families"],
                                    "p_value": exact["p_value"]},
                "paired_positions": {"wins": wins, "losses": losses, "net": wins - losses, "positions": positions},
                "unknown_sensitivity_mean_bounds": ([sum(low) / len(low), sum(high) / len(high)] if kept else None),
                "direction": "treatment_higher" if total > 0 else "control_higher" if total < 0 else "equal",
                # only a primary (bound - base) contrast can be supported; every other contrast is descriptive even
                # when its block signs happen to agree
                "supported": bool(primary and differences and total != 0
                                  and exact["p_value"] <= spec["analysis"]["confirmatory"]["alpha"])}

    contrasts = [contrast(t, c) for t, c in spec["analysis"]["contrasts"]]
    arms = {}
    for arm in ARMS:
        base = BOUND.get(arm, arm)
        totals = {k: sum(o["arms"][arm][k] for o in outcomes) for k in ("pass", "fail", "unknown", "positions")}
        arms[arm] = {**totals, "yield": totals["pass"] / totals["positions"],
                     "dispositions": {status: sum(c["dispositions"][arm]["status"] == status for c in candidates)
                                      for status in sorted({c["dispositions"][arm]["status"] for c in candidates})},
                     "authorized_blocks": sum(c["verifier"][base]["authorized"] for c in candidates) if base in TEXT_ARMS else None,
                     "binding_applied_blocks": sum(c["dispositions"][arm]["binding_applied"] for c in candidates),
                     "blocks_with_feedback": sum(c["dispositions"][arm]["traces_with_feedback"] > 0 for c in candidates)}
    parent = {k: sum(o["evaluations"]["parent"][k] for o in outcomes) for k in ("pass", "fail", "unknown", "positions")}
    component = {arm: {k: sum(c["verifier"][arm]["all_eligible_rows"][k] for c in candidates) for k in (
        "rejected_host_fail_rows", "eligible_host_fail_rows", "rejected_host_pass_rows", "eligible_host_pass_rows")}
        for arm in TEXT_ARMS}
    for arm, v in component.items():
        v["detection_rate"] = v["rejected_host_fail_rows"] / v["eligible_host_fail_rows"] if v["eligible_host_fail_rows"] else None
        v["false_rejection_rate"] = v["rejected_host_pass_rows"] / v["eligible_host_pass_rows"] if v["eligible_host_pass_rows"] else None
    return {"contrasts": contrasts, "arms": arms, "parent": parent, "verifier_component": component,
            "blocks": len(outcomes), "claim_limits": spec["analysis"]["claim_limits"]}


# ----------------------------------------------------------------------------- run / verify
CODE_ENTRIES = ("skillopt/feedback_study/rubric_binding.py", "scripts/run_rubric_binding_study.py")


def code_closure():
    """``matched_feedback.code_closure`` for this study's entries (the same walk)."""
    from .matched_feedback import code_closure as walk
    import skillopt.feedback_study.matched_feedback as mf

    saved = mf.CODE_ENTRIES
    try:
        mf.CODE_ENTRIES = CODE_ENTRIES
        return walk()
    finally:
        mf.CODE_ENTRIES = saved


def _manifest(spec, panel):
    template = {k: v for k, v in spec["template"].items() if k != "panel_hash"}
    return study_manifest({**template, "panel": panel}, spec["budget"],
                          {"protocol": PROTOCOL, "protocol_hash": spec["record_hash"],
                           "study_sources": study_sources(MODULES), "native_sources": native_sources(),
                           "code_closure": code_closure()})


def verify_result(output):
    root = safe_path(output)
    saved = read_json(root / "result.json", sealed=True)
    protocol = read_json(root / "protocol.json", sealed=True)
    value = read_json(root / "study.json", sealed=True)
    require(saved["version"] == protocol["protocol"] == PROTOCOL and saved["protocol_hash"] == protocol["record_hash"]
            and saved["study_hash"] == value["record_hash"] and value["study"]["protocol_hash"] == protocol["record_hash"]
            and value["study"]["protocol"] == PROTOCOL and saved["status"] in {"completed", "pending"}
            and saved["artifacts"] == rf._artifacts(root, Ledger(root, value, None)),
            "The finished study's bindings or evidence inventory changed")
    return saved


def run_study(spec, panel, output, *, repo=None, fixture_api=None, fixture_evaluate=None):
    validate_spec(spec)
    require(digest(panel) == spec["template"]["panel_hash"], "The panel is not the registered panel")
    root = safe_path(output)
    with output_lock(root):
        if (root / "result.json").exists():
            saved = verify_result(root)
            require(saved["protocol_hash"] == spec["record_hash"], "The finished study belongs to another protocol")
            return saved
        if (root / "started.json").exists():
            return {"status": "pending", "reason": "interrupted_study_no_automatic_resume", "model_calls_submitted": 0}
        value = _manifest(spec, panel)
        if (root / "protocol.json").exists() or (root / "study.json").exists():
            require(read_json(root / "protocol.json", sealed=True) == spec
                    and read_json(root / "study.json", sealed=True) == value,
                    "The prepared protocol or manifest (implementation identity) differs from the current rebuild")
        fixture = value["model"]["provider"] == "fixture"
        require(fixture == (fixture_api is not None and fixture_evaluate is not None)
                and (fixture or (fixture_api is None and fixture_evaluate is None)),
                "Fixture hooks belong to a fixture study only")
        write_json(root / "protocol.json", spec)
        write_json(root / "study.json", value)
        write_json(root / "panel.json", panel)
        if not fixture:
            require(repo is not None, "A natural study needs the credential repository")
            require(backends.readiness(spec["benchmark"], value["runtime"])["status"] == "ready", "Runtime is not ready")
        started = seal({"protocol_hash": spec["record_hash"], "study_hash": value["record_hash"],
                        "started_at": datetime.now(timezone.utc).isoformat(timespec="seconds")})
        write_json(root / "started.json", started)
        api, pending = fixture_api, None
        families = set(value["train_families"])
        train = [{"role": "train", "task": t} for t in panel["tasks"] if t["family_id"] in families]
        selection = [{"role": "selection", "task": t} for t in panel["tasks"] if t["family_id"] not in families]
        candidates, outcomes = [], []
        try:
            if not fixture:
                model = value["model"]
                api = CachedAPI(Path(repo), root / "api", provider=model["provider"], model=model["name"], workers=1,
                                reasoning_effort=model["reasoning_effort"],
                                **model.get("transport", {"initial_health_policy": "completed_response_v1"}),
                                **({"proxy": model["proxy"]} if "proxy" in model else {}), **client_options(value))
            write_json(root / "model_service.json", seal(api.service))
            ledger = Ledger(root, value, api)
            adapter = Adapter(value, root, ledger, fixture_evaluate=fixture_evaluate)
            for block in range(spec["blocks"]):
                frozen, outcome = run_block(spec, value, root, ledger, adapter, train, selection, block,
                                            value["recovery_policy"]["verifier_workers"])
                candidates.append(frozen)
                outcomes.append(outcome)
        except LearningPending as exc:
            pending = str(exc)
        except Exception as exc:  # the type only: provider text never enters a record
            pending = "error:" + type(exc).__name__
        finally:
            if api is not None and not fixture:
                api.close()
        ledger = Ledger(root, value, None)
        costs = ledger.snapshot()
        if pending is None and (costs.get("unclosed_calls") != 0 or ledger.usage_blocks_completion(costs)):
            pending = "usage_or_receipt_accounting_incomplete"
        analysis = analyze(spec, candidates, outcomes) if pending is None else None
        result = seal({"version": PROTOCOL, "protocol_hash": spec["record_hash"], "study_hash": value["record_hash"],
                       "status": "completed" if pending is None else "pending", "reason": pending,
                       "completed_blocks": len(outcomes), "blocks": spec["blocks"],
                       **({} if analysis is None else analysis), "costs": costs,
                       "artifacts": rf._artifacts(root, ledger), "deployment_authorized": False})
        write_json(root / "result.json", result)
        return result
