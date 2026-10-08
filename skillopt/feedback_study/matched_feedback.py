"""L3 matched one-step feedback study (``fivebench-matched-feedback-study-v1``; registered 10/8, Codex design round
post-S3-2). A validation-only mechanism experiment; it never changes a frozen stage, the main table or S3.

Eight blocks, each from the SAME frozen parent Skill (the main method's S2): one fresh shared train rollout (common
known-row mask, scalar feedback, ordering and minibatch seed), judged by the frozen default and h2 KOR rubrics (each
calibrated by the frozen v7 authorization rule), then ONE native proposal per arm --
  scalar  : scalar feedback only                                          (arm A)
  default : + authorized default-rubric reports and rubric guidance       (arm B)
  h2      : + authorized h2-rubric reports and rubric guidance             (arm C)
-- an unauthorized verifier arm keeps its scheduled independent proposal draw with scalar-equivalent input. Every
candidate and disposition is frozen before any validation; every admissible changed candidate and the common parent
are then evaluated once on the full validation panel (no screening, randomized slot order); no-update and
inadmissible proposals fall back to the parent's pass. Primary: per-block verified-success yield difference h2 -
scalar, exact two-sided sign-flip over the eight blocks (alpha 0.05, positive for a directional claim). No test
evaluation, no main-table or S3 change; an interruption is pending, never resumed, no replacement block.
"""
from __future__ import annotations

import hashlib
import math
import random
import warnings
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

from skillopt.coevolution_v5.core import seal, verify
from skillopt.continual_eval import backends
from skillopt.continual_eval.core import output_lock, read_json, require, safe_path, write_json
from skillopt.continual_learning.contracts import VERIFIER_METHOD, check_skill, skill_budget
from skillopt.continual_learning.feedback import artifacts as learning_artifacts
from skillopt.continual_learning.feedback import benchmark_for, project, task_description, verifier_enabled
from skillopt.continual_learning.gepa import Adapter
from skillopt.continual_learning.ledger import LearningPending, Ledger
from skillopt.continual_learning.recovery import DELIVERY_VERSIONS, POLICY_V10, client_options
from skillopt.continual_learning.skillopt import native_sources
from skillopt.continual_learning.verifier import default_policy_record
from skillopt.validator_pilot.api import CachedAPI, digest

from .common import FixedRubricVerifier, bind_rows, run_cells, study_manifest, study_sources, validate_rubric_record
from .fixed_rubric import sign_flip_two_sided

PROTOCOL = "fivebench-matched-feedback-study-v1"
BENCHMARK = "korbench"
ARMS = ("scalar", "default", "h2")
VERIFIER_ARMS = ("default", "h2")
SLOTS = ("parent", *ARMS)  # validation evaluation slots of a block
BLOCKS = 8
MODULES = ("__init__.py", "common.py", "fixed_rubric.py", "matched_feedback.py")
PLAN_SEED = 20261011
EDIT_BUDGET = 4
BUDGET = {"max_metric_calls": 9000, "max_reflection_calls": 800, "max_api_calls": 20000,
          "max_reported_tokens": 80_000_000, "max_iterations": 1, "minibatch_size": 8, "solver_max_tokens": 65536,
          "reflection_max_tokens": 8192, "max_verifier_calls": 5760, "verifier_max_tokens": 4096}
ANALYSIS = {
    "unit": "block",
    "endpoint": "verified_success_yield = passes / planned_validation_positions (unknown is its own state)",
    "fallback": "no_update_or_inadmissible_proposal_is_scored_by_the_block_parent_pass_with_its_disposition_recorded",
    "primary": {"treatment": "h2", "control": "scalar", "statistic": "per_block_pass_difference",
                "test": "exact_two_sided_sign_flip_over_blocks", "alpha": 0.05,
                "directional_claim": "mean_difference_positive_and_p_at_most_alpha"},
    "secondary": [["default", "scalar"], ["h2", "default"]],
    "secondary_rule": "descriptive_without_multiplicity_adjustment; no rubric-evolution claim without a convincing h2-default contrast",
    "unauthorized_verifier_arm": "reports_and_rubric_guidance_removed_independent_proposal_draw_kept_no_retry",
    "candidate_screen": "none_no_arm_sees_a_label",
    "descriptive": ["authorization_rates", "dispositions", "candidate_bytes", "pass_fail_unknown_by_arm",
                    "unknown_as_pass_or_fail_sensitivity", "default_vs_h2_judgments_on_identical_rows",
                    "costs_shared_counted_once"],
    "prohibited": ["test_evaluation", "main_table_or_s3_change", "replacement_or_extra_blocks", "resuming",
                   "favorable_subgroup_substitution", "switching_the_h2_record", "v9_screening_of_candidates"],
    "completion": "frozen_v10_ledger_blocking_usage_gap_rule_bounded_unknown_cost_attempts_reported",
}


def build_spec(template, rubrics, source):
    spec = seal({"protocol": PROTOCOL, "benchmark": BENCHMARK, "arms": list(ARMS), "blocks": BLOCKS,
                 "rubrics": {arm: rubrics[arm] for arm in VERIFIER_ARMS},
                 "rubric_policy_hashes": {arm: rubrics[arm]["policy_hash"] for arm in VERIFIER_ARMS},
                 "template": template, "budget": dict(BUDGET), "plan_seed": PLAN_SEED, "edit_budget": EDIT_BUDGET,
                 "analysis": ANALYSIS, "source": source,
                 "information_origin": "fresh_train_rollouts_scalar_host_feedback_label_free_verifier_reports",
                 "deployment_authorized": False})
    validate_spec(spec)
    return spec


def validate_spec(spec):
    verify(spec)
    require(spec["protocol"] == PROTOCOL and spec["benchmark"] == BENCHMARK and spec["arms"] == list(ARMS)
            and spec["blocks"] == BLOCKS and spec["budget"] == BUDGET and spec["plan_seed"] == PLAN_SEED
            and spec["edit_budget"] == EDIT_BUDGET and spec["analysis"] == ANALYSIS
            and set(spec["rubrics"]) == set(VERIFIER_ARMS), "Not this study's registered protocol")
    for arm in VERIFIER_ARMS:
        validate_rubric_record(spec["rubrics"][arm], BENCHMARK)
        require(spec["rubric_policy_hashes"][arm] == spec["rubrics"][arm]["policy_hash"], "Rubric hash registry differs")
    require(spec["rubrics"]["default"] == default_policy_record(BENCHMARK)
            and spec["rubrics"]["h2"]["status"] == "update"
            and spec["rubrics"]["h2"]["policy_hash"] != spec["rubrics"]["default"]["policy_hash"],
            "The arms are the frozen default and the recorded final evolved rubric")
    template = spec["template"]
    require(set(template) == {"panel_hash", "train_families", "selection_families", "model", "runtime", "parent_skill",
                              "seed", "recovery_policy"}
            and template["recovery_policy"] == POLICY_V10, "The template is not a v10 (v7 delivery) source template")
    return spec


def block_plan(spec, block):
    """Every randomized choice of a block, derived from the registered seed before any call."""
    rng = random.Random(digest({"plan_seed": spec["plan_seed"], "block": block}))
    proposal_order, evaluation_order = list(ARMS), list(SLOTS)
    rng.shuffle(proposal_order)
    rng.shuffle(evaluation_order)
    return {"block": block, "train_rollout": block, "minibatch_seed": rng.randrange(2**31),
            "judge_seed": rng.randrange(2**31), "proposal_order": proposal_order, "evaluation_order": evaluation_order,
            "validation_rollouts": {slot: 1 + len(SLOTS) * block + index for index, slot in enumerate(SLOTS)}}


# ----------------------------------------------------------------------------- one arm's native proposal
def _authenticate_arm(ledger, verifier_root, label, policy_record):
    """The rubric text an arm's analysts see must be that arm's frozen rubric, whose block calibration (same manifest,
    same verifier record tree) authorized it."""
    summary = read_json(safe_path(verifier_root) / "summary.json", sealed=True)
    require(summary["manifest_hash"] == ledger.manifest["record_hash"] and summary["step"] == label
            and summary["policy_hash"] == policy_record["policy_hash"] == digest(policy_record["policy"])
            and summary["authorized"] is True, "The arm's rubric is not its block's authorized frozen rubric")


def _bind_arm_traces(traces, ledger, parent_skill, rollout, label, verifier_root=None, verifier_reports=None,
                     policy_record=None):
    """``skillopt._bind_traces`` for one arm: every trace is the block's sealed fresh train evidence of the parent,
    its scalar projection recomputed; a verifier text must equal the arm's sealed authorized report."""
    panel = read_json(ledger.root / "panel.json")
    require(digest(panel) == ledger.manifest["panel_hash"], "Feedback panel is not authorized")
    tasks = {digest(task): task for task in panel["tasks"]}
    evidence = {}
    for path in sorted((ledger.root / "evaluations").glob("*.json")):
        row = read_json(path, sealed=True)
        evidence[row["record_hash"]] = (path, row)
    for trace in traces:
        require(trace["evidence_hash"] in evidence, "Feedback has no current learning execution evidence")
        path, row = evidence[trace["evidence_hash"]]
        request = row["request"]
        task = tasks.get(request["task_hash"])
        require(task is not None and request["manifest_hash"] == ledger.manifest["record_hash"]
                and request["role"] == "train" and task["partition"] == "development"
                and ledger.manifest["authorized_tasks"].get(request["task_hash"]) == "train"
                and request["candidate_hash"] == digest({"skill": parent_skill}) and request.get("rollout") == rollout
                and read_json(ledger.root / "evaluation_intents" / path.name, sealed=True) == seal(request),
                "Feedback role, task, parent, rollout or authorization mismatch")
        expected = project(ledger.manifest, task["public"], row["prediction"], row["score"],
                           private=task["private"], role="train")
        feedback = dict(trace["Feedback"])
        if "verifier" in feedback:
            require(verifier_reports is not None and policy_record is not None
                    and trace["evidence_hash"] in verifier_reports, "Verifier feedback without a sealed report")
            report = read_json(safe_path(verifier_root) / "reports" / (trace["evidence_hash"] + ".json"), sealed=True)
            require(report == verifier_reports[trace["evidence_hash"]]
                    and report["manifest_hash"] == ledger.manifest["record_hash"] and report["step"] == label
                    and report["policy_hash"] == policy_record["policy_hash"] and report["authorized"] is True
                    and report["feedback"] == feedback.pop("verifier") and report["evidence_hash"] == trace["evidence_hash"],
                    "Verifier feedback differs from the arm's sealed report")
        require({**{key: trace[key] for key in expected if key != "Feedback"}, "Feedback": feedback} == expected,
                "Feedback projection differs from actual execution")


def propose_arm(parent_skill, traces, output, ledger, *, label, rollout, seed, minibatch_size, edit_budget=EDIT_BUDGET,
                verifier_root=None, verifier_reports=None, policy_record=None):
    """``skillopt.propose_native`` for one study arm, step for step: the same analyst systems, native
    reflect -> merge -> rank -> apply pipeline, parser, retries, fallback provenance and admissibility. Only the
    identity label (``skillopt:<label>:...`` logical ids, so arms never share a cache identity) and the report tree
    the verifier text is bound to (the arm's own frozen-rubric records) differ."""
    from skillopt.continual_learning.skillopt import (VERIFIER_IMPLEMENTATION, VERIFIER_PREAMBLE_VERSION, _analyst_systems,
                                                      _checker_note, _NativeBridge, _transport, _validate_traces,
                                                      native_sources)
    from skillopt.continual_learning.transfer import TRANSFER_PREAMBLE_VERSION
    from skillopt.engine.trainer import _normalise_patches
    from skillopt.gradient import aggregate, reflect
    from skillopt.optimizer import clip
    from skillopt.optimizer.skill import apply_patch_with_report

    check_skill(parent_skill, skill_budget(ledger.manifest))
    benchmark = benchmark_for(ledger.manifest)
    require(verifier_enabled(ledger.manifest) and ledger.manifest.get("method") == VERIFIER_METHOD,
            "The study runs under the v10 verifier-feedback manifest")
    _validate_traces(traces, benchmark, verifier=True)
    require((verifier_root is None) == (verifier_reports is None) == (policy_record is None),
            "An arm has all of root, reports and rubric or none")
    require(policy_record is not None or not any("verifier" in t["Feedback"] for t in traces),
            "Verifier reports need the arm's authorized rubric")
    if policy_record is not None:
        _authenticate_arm(ledger, verifier_root, label, policy_record)
    _bind_arm_traces(traces, ledger, parent_skill, rollout, label, verifier_root, verifier_reports, policy_record)
    require(type(seed) is int and seed >= 0, "Invalid seed")
    require(type(minibatch_size) is int and 1 <= minibatch_size <= 64, "Invalid native minibatch size")
    require(type(edit_budget) is int and 1 <= edit_budget <= 16, "Invalid native edit budget")
    systems = _analyst_systems(ledger.manifest, policy_record)
    root = safe_path(output)
    identity = seal({"parent_skill": parent_skill, "traces_hash": digest(traces),
                     "manifest_hash": ledger.manifest["record_hash"], "native_sources": native_sources(),
                     "step": label, "rollout": rollout, "seed": seed, "minibatch_size": minibatch_size,
                     "edit_budget": edit_budget, "meta": False, "slow": False, "skill_aware": False,
                     "native_generic_prompts": not systems, "acceptance": "none_one_step_matched_study",
                     "analyst_preamble": TRANSFER_PREAMBLE_VERSION, "analyst_systems": digest(systems),
                     "verifier": VERIFIER_IMPLEMENTATION, "verifier_preamble": VERIFIER_PREAMBLE_VERSION,
                     "verifier_authorized": policy_record is not None,
                     "verifier_policy_hash": policy_record["policy_hash"] if policy_record else None,
                     "verifier_reports_hash": digest({k: v["record_hash"] for k, v in sorted((verifier_reports or {}).items())})})
    write_json(root / "identity.json", identity)
    if (root / "result.json").exists():
        result = read_json(root / "result.json", sealed=True)
        require(result["identity_hash"] == identity["record_hash"], "Native proposal identity differs")
        return result
    if (root / "started.json").exists():
        raise LearningPending("native_proposal_interrupted_no_automatic_resume")
    write_json(root / "started.json", seal({"identity_hash": identity["record_hash"]}))
    native_rows = []
    for trace in traces:
        token = trace["evidence_hash"]
        description = task_description(benchmark, trace["Inputs"])
        write_json(root / "predictions" / token / "conversation.json", [
            {"role": "user", "content": description},
            {"role": "assistant", "content": trace["Generated Outputs"]},
            {"role": "system", "content": _checker_note(trace["Feedback"])},
        ])
        native_rows.append({"id": token, "hard": trace["Feedback"]["score"], "n_turns": 1,
                            "task_description": description, "task_type": benchmark,
                            "fail_reason": "Native development check failed"
                            if trace["Feedback"]["status"] == "fail" else ""})
    bridge = _NativeBridge(ledger, label, audit_root=root / "parser_audits")
    with _transport(bridge), warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        raw = sorted(reflect.run_minibatch_reflect(
            native_rows, parent_skill, str(root / "predictions"), str(root / "patches"),
            workers=1, failure_only=False, minibatch_size=minibatch_size, edit_budget=edit_budget,
            random_seed=seed, error_system=systems.get("error_system"),
            success_system=systems.get("success_system"), update_mode="patch",
            step_buffer_context="", meta_skill_context="", skill_aware_reflection=False), key=digest)
        if bridge.failure is not None:
            raise LearningPending("native_reflection_incomplete") from bridge.failure
        expected = sum(math.ceil(sum(row["hard"] == value for row in native_rows) / minibatch_size) for value in (0, 1))
        if len(raw) != expected:
            raise LearningPending("native_reflection_parse_incomplete")
        failure, success = _normalise_patches(deepcopy(raw), update_mode="patch")
        merged = aggregate.merge_patches(parent_skill, failure, success, batch_size=8,
                                         workers=1, verbose=False, update_mode="patch")
        selected = clip.rank_and_select(parent_skill, merged, max_edits=edit_budget, update_mode="patch")
    if bridge.failure is not None:
        raise LearningPending("native_optimizer_incomplete") from bridge.failure
    require(ledger.manifest["version"] in DELIVERY_VERSIONS, "Fallback provenance is a v5+ record")
    fallbacks = sorted({str(w.message) for w in caught if "using fallback" in str(w.message)})
    if "[fallback truncated" in str(selected.get("reasoning", "")):
        fallbacks.append("ranking fallback truncation")
    candidate, application = apply_patch_with_report(parent_skill, selected)
    try:
        check_skill(candidate, skill_budget(ledger.manifest))
    except ValueError as exc:
        oversized = type(candidate) is str and len(candidate.encode("utf-8")) > skill_budget(ledger.manifest)
        if not oversized:
            raise LearningPending("native_candidate_exceeds_skill_budget") from exc
        result = seal({"identity_hash": identity["record_hash"], "candidate_skill": parent_skill,
                       "status": "rejected_inadmissible_over_budget",
                       "rejected_candidate_skill": candidate, "rejected_candidate_hash": digest(candidate),
                       "rejected_candidate_bytes": len(candidate.encode("utf-8")),
                       "raw": raw, "merged": merged, "selected": selected, "application": application,
                       "optimizer_calls": bridge.calls, "native_fallbacks": fallbacks, "deployment_authorized": False})
        write_json(root / "result.json", result)
        return result
    result = seal({"identity_hash": identity["record_hash"], "candidate_skill": candidate,
                   "status": "candidate_ready" if candidate != parent_skill else "no_update",
                   "raw": raw, "merged": merged, "selected": selected, "application": application,
                   "optimizer_calls": bridge.calls, "native_fallbacks": fallbacks, "deployment_authorized": False})
    write_json(root / "result.json", result)
    return result


# ----------------------------------------------------------------------------- one block
def _counts(rows):
    return {"positions": len(rows), "pass": sum(r["score"] == 1 for r in rows),
            "fail": sum(r["score"] == 0 for r in rows), "unknown": sum(r["score"] is None for r in rows),
            "evidence_digest": digest([r["output"]["evidence_hash"] for r in rows])}


def run_block(spec, value, root, ledger, adapter, train, selection, block, workers):
    """One matched block: shared fresh train rollout -> default/h2 judgments and calibration -> one native proposal
    per arm (registered order) -> candidates and dispositions frozen -> full validation passes (registered order)."""
    from .fixed_rubric import arm_metrics

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
    cells = [[arm, token] for token in tokens for arm in VERIFIER_ARMS]
    random.Random(plan["judge_seed"]).shuffle(cells)
    write_json(folder / "schedule.json", seal({"protocol_hash": spec["record_hash"], "block": block,
                                               "eligible_tokens": tokens, "cells": cells}))
    verifiers = {arm: FixedRubricVerifier(value, ledger, root, rollout, arm, spec["rubrics"][arm]) for arm in VERIFIER_ARMS}
    records = run_cells([tuple(cell) for cell in cells], verifiers, by_token, workers)
    summaries, reports = {}, {}
    for arm in VERIFIER_ARMS:
        summaries[arm], reports[arm] = verifiers[arm].calibrate([records[arm][t] for t in
                                                                 (row["output"]["evidence_hash"] for _, row in pairs)])
    meta = [{"token": row["output"]["evidence_hash"], "family": item["task"]["family_id"],
             "host_status": "fail" if row["score"] == 0 else "pass"} for item, row in pairs]
    proposals, injected = {}, {}
    for arm in plan["proposal_order"]:
        arm_traces, kwargs = deepcopy(traces), {}
        if arm in VERIFIER_ARMS and summaries[arm]["authorized"]:
            # exactly run_stage's injection: the authorized sealed report text of failed rows, and the rubric record
            for trace in arm_traces:
                report = reports[arm].get(trace["evidence_hash"])
                if (trace["Feedback"]["status"] == "fail" and report is not None and report["authorized"]
                        and report["feedback"] is not None):
                    trace["Feedback"] = {**trace["Feedback"], "verifier": report["feedback"]}
            kwargs = {"verifier_root": verifiers[arm].root, "verifier_reports": reports[arm],
                      "policy_record": verifiers[arm].rubric}
        injected[arm] = sum("verifier" in t["Feedback"] for t in arm_traces)
        proposals[arm] = propose_arm(parent, arm_traces, root / "native" / str(block) / arm, ledger,
                                     label=f"{rollout}-{arm}", rollout=rollout, seed=plan["minibatch_seed"],
                                     minibatch_size=value["budget"]["minibatch_size"], edit_budget=spec["edit_budget"],
                                     **kwargs)
    dispositions = {}
    for arm in ARMS:
        proposal = proposals[arm]
        changed = proposal["status"] == "candidate_ready"
        dispositions[arm] = {"proposal_hash": proposal["record_hash"], "status": proposal["status"],
                             "candidate_hash": digest(proposal["candidate_skill"]) if changed else None,
                             "candidate_bytes": len(proposal["candidate_skill"].encode()) if changed else None,
                             "rejected_candidate_hash": proposal.get("rejected_candidate_hash"),
                             "evaluated": "candidate" if changed else "parent_fallback",
                             "verifier_authorized": summaries[arm]["authorized"] if arm in VERIFIER_ARMS else None,
                             "traces_with_verifier_report": injected[arm],
                             "rubric_guidance": arm in VERIFIER_ARMS and summaries[arm]["authorized"],
                             "native_fallbacks": proposal["native_fallbacks"]}
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
                                    for arm in VERIFIER_ARMS},
                       "dispositions": dispositions, "frozen_before_validation": True})
    write_json(folder / "candidates.json", candidates)  # every candidate and disposition, before any validation
    evaluations = {}
    for slot in plan["evaluation_order"]:
        if slot == "parent":
            skill = parent
        elif dispositions[slot]["evaluated"] == "candidate":
            skill = proposals[slot]["candidate_skill"]
        else:
            continue  # scored by the block's parent pass
        rows = adapter.evaluate_rows(selection, {"skill": skill}, rollout=plan["validation_rollouts"][slot])
        evaluations[slot] = {"skill_hash": digest(skill), "rollout": plan["validation_rollouts"][slot], **_counts(rows)}
    arms = {arm: {**(evaluations[arm] if dispositions[arm]["evaluated"] == "candidate" else evaluations["parent"]),
                  "evaluated": dispositions[arm]["evaluated"]} for arm in ARMS}
    outcome = seal({"protocol_hash": spec["record_hash"], "block": block, "candidates_hash": candidates["record_hash"],
                    "evaluations": evaluations, "arms": arms})
    write_json(folder / "outcome.json", outcome)
    return candidates, outcome


# ----------------------------------------------------------------------------- analysis (pure, zero calls)
def analyze(spec, candidates, outcomes):
    analysis = spec["analysis"]
    alpha = analysis["primary"]["alpha"]
    positions = outcomes[0]["evaluations"]["parent"]["positions"]

    def contrast(treatment, control):
        differences = [o["arms"][treatment]["pass"] - o["arms"][control]["pass"] for o in outcomes]
        exact = sign_flip_two_sided(differences)  # the same exact convolution as L1, over blocks instead of families
        flip = {"observed_sum": exact["observed_sum"], "informative_blocks": exact["informative_families"],
                "p_value": exact["p_value"], "method": "exact_block_sign_flip_convolution"}
        mean = sum(differences) / len(differences)
        # unknown sensitivity: every unknown of the treatment counted fail and of the control pass, and vice versa
        low = [o["arms"][treatment]["pass"] - o["arms"][control]["pass"] - o["arms"][control]["unknown"] for o in outcomes]
        high = [o["arms"][treatment]["pass"] + o["arms"][treatment]["unknown"] - o["arms"][control]["pass"] for o in outcomes]
        return {"treatment": treatment, "control": control, "differences": differences, "mean_difference": mean,
                "mean_yield_difference": mean / positions, **flip,
                "unknown_sensitivity_mean_bounds": [sum(low) / len(low), sum(high) / len(high)]}

    primary = {**analysis["primary"], **contrast(analysis["primary"]["treatment"], analysis["primary"]["control"])}
    primary["supported"] = bool(primary["mean_difference"] > 0 and primary["p_value"] <= alpha)
    secondary = [contrast(t, c) for t, c in analysis["secondary"]]
    arms = {}
    for arm in ARMS:
        totals = {k: sum(o["arms"][arm][k] for o in outcomes) for k in ("pass", "fail", "unknown", "positions")}
        arms[arm] = {**totals, "yield": totals["pass"] / totals["positions"],
                     "dispositions": {status: sum(c["dispositions"][arm]["status"] == status for c in candidates)
                                      for status in sorted({c["dispositions"][arm]["status"] for c in candidates})},
                     "authorized_blocks": (sum(c["verifier"][arm]["authorized"] for c in candidates)
                                           if arm in VERIFIER_ARMS else None)}
    component = [{"block": c["block"], **{arm: {k: c["verifier"][arm]["all_eligible_rows"][k] for k in (
        "rejected_host_fail_rows", "eligible_host_fail_rows", "rejected_host_pass_rows", "eligible_host_pass_rows")}
        for arm in VERIFIER_ARMS}} for c in candidates]
    wording = ("evolved_verifier_feedback_improved_one_step_proposals_over_scalar" if primary["supported"]
               else "no_supported_difference_over_scalar")
    return {"primary": primary, "secondary": secondary, "arms": arms, "verifier_component": component,
            "blocks": len(outcomes), "registered_wording": wording}


# ----------------------------------------------------------------------------- run / verify
CODE_ENTRIES = ("skillopt/feedback_study/matched_feedback.py", "scripts/run_fivebench_matched_feedback_study.py")


def code_closure():
    """Every repository module the paid L3 run can execute, by content hash: the transitive closure of the imports
    (``skillopt.*`` and ``scripts.*``; absolute and relative with level arithmetic; function-level imports; every
    enclosing package ``__init__``) of this study module, its CLI and the native updater's entry modules
    (``native_sources()``) -- study harness, judge/ledger/solver adapter, seal/verify helpers, orchestration scripts and
    the native updater with its prompt loader (Codex reviews L3-3/L3-4). Data files are bound elsewhere: prompt texts
    by ``native_sources()``, benchmark assets and runtime by the base manifest. A new import enters automatically."""
    import ast

    repo = Path(__file__).resolve().parents[2]

    def target(name):
        parts = name.split(".")
        if parts[0] not in {"skillopt", "scripts"}:
            return None
        path = repo.joinpath(*parts)
        return path.with_suffix(".py") if path.with_suffix(".py").is_file() else (
            path / "__init__.py" if (path / "__init__.py").is_file() else None)

    todo = [repo / entry for entry in CODE_ENTRIES]
    todo += [repo / "skillopt" / name for name in native_sources() if name.endswith(".py")]
    seen = set()
    while todo:
        path = todo.pop()
        if path in seen:
            continue
        seen.add(path)
        relative = path.relative_to(repo)
        for depth in range(1, len(relative.parts)):  # enclosing package __init__ files run on import
            init = repo.joinpath(*relative.parts[:depth], "__init__.py")
            if init.is_file():
                todo.append(init)
        module = list(relative.with_suffix("").parts)
        if module[-1] == "__init__":
            module = module[:-1]
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            names = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    base = module[: len(module) - node.level + (path.name == "__init__.py")]
                    prefix = ".".join(base + ([node.module] if node.module else []))
                else:
                    prefix = node.module or ""
                names = [prefix] + [prefix + "." + alias.name for alias in node.names]
            for name in names:
                found = target(name)
                if found is not None and found not in seen:
                    todo.append(found)
    return {str(path.relative_to(repo)): hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(seen)}


def _manifest(spec, panel):
    """The prepared identity binds the learning sources (base manifest), this study's modules, the native updater's
    prompt texts and modules (native_sources) and the whole executed code closure (code_closure) -- all checked before
    any client or call."""
    template = {k: v for k, v in spec["template"].items() if k != "panel_hash"}
    return study_manifest({**template, "panel": panel}, spec["budget"],
                          {"protocol": PROTOCOL, "protocol_hash": spec["record_hash"],
                           "study_sources": study_sources(MODULES), "native_sources": native_sources(),
                           "code_closure": code_closure()})


def _artifacts(root, ledger):
    """The v10 governed inventory (receipts, intents, evaluations, verifier records, calibration) plus the study's
    protocol/manifest/panel/markers/service and every block and native proposal record."""
    files = ("protocol.json", "study.json", "panel.json", "started.json", "model_service.json")
    result = {**learning_artifacts(ledger),
              **{name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in files if (root / name).exists()}}
    result.update({str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
                   for folder in ("blocks", "native") for p in sorted((root / folder).rglob("*")) if p.is_file()})
    return result


def verify_result(output):
    """Read-only, zero-call check of a finished study against its OWN sealed protocol and manifest (never a rebuild):
    bindings and the exact governed artifact inventory (a changed, missing or extra file fails)."""
    root = safe_path(output)
    saved = read_json(root / "result.json", sealed=True)
    protocol = read_json(root / "protocol.json", sealed=True)
    value = read_json(root / "study.json", sealed=True)
    require(saved["version"] == protocol["protocol"] == PROTOCOL and saved["protocol_hash"] == protocol["record_hash"]
            and saved["study_hash"] == value["record_hash"] and value["study"]["protocol_hash"] == protocol["record_hash"]
            and value["study"]["protocol"] == PROTOCOL and saved["status"] in {"completed", "pending"}
            and saved["artifacts"] == _artifacts(root, Ledger(root, value, None)),
            "The finished study's bindings or evidence inventory changed")
    return saved


def run_study(spec, panel, output, *, repo=None, fixture_api=None, fixture_evaluate=None):
    """Run the registered study once into ``output``; returns its sealed result (completed or pending)."""
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
            # a prepared study runs only with the implementation identity it was prepared with (code review round
            # L3-1): the sealed manifest binds the learning sources and this study's own modules
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
            require(backends.readiness(BENCHMARK, value["runtime"])["status"] == "ready",
                    "KOR-Bench native runtime is not ready")
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
        finally:
            if api is not None and not fixture:
                api.close()
        ledger = Ledger(root, value, api)
        costs = ledger.snapshot()
        if pending is None and ledger.usage_blocks_completion(costs):
            pending = "incomplete_usage"
        if pending is None:
            intents = {p.name for p in (root / "evaluation_intents").glob("*.json")}
            if intents != {p.name for p in (root / "evaluations").glob("*.json")}:
                pending = "evaluation_without_receipt"
        outcome = {"version": PROTOCOL, "protocol_hash": spec["record_hash"], "study_hash": value["record_hash"],
                   "started_at": started["started_at"],
                   "finished_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                   "completed_blocks": len(outcomes), "costs": costs, "usage_complete": costs["usage_complete"],
                   "unknown_cost_attempts": costs["unknown_cost_attempts"],
                   "completion_rule": spec["analysis"]["completion"], "deployment_authorized": False}
        if pending is not None:
            outcome.update(status="pending", reason=pending, artifacts=_artifacts(root, ledger))
        else:
            outcome.update(status="completed", **analyze(spec, candidates, outcomes),
                           block_records=[{"candidates_hash": c["record_hash"], "outcome_hash": o["record_hash"]}
                                          for c, o in zip(candidates, outcomes)],
                           artifacts=_artifacts(root, ledger))
        frozen = seal(outcome)
        write_json(root / "result.json", frozen)
        return frozen
