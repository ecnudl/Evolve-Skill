"""Read-only analysis of a completed mechanism pilot, never an experiment runner.

Retains the original panel and adds a separately preregistered task sensitivity
view. No API cache, raw audit, solver, updater or incomplete run is inspected.
Content seals establish consistency, not authenticity or semantic independence.
An optional immutable JSON export must live outside the analyzed run; source
records and the sensitivity plan are never overwritten.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

from skillopt.coevolution_v5.core import seal, verify
from skillopt.skill_validation.mechanism_metrics import CONDITIONS, EXPOSURES, _grid, summarize
from skillopt.skill_validation.models import require
from skillopt.skill_validation.panel import checked_path
from skillopt.skill_validation.rule_skill import RuleSkill, render_skill
from skillopt.validator_pilot.api import digest, write_immutable_json

VERSION = "completed-mechanism-pilot-sensitivity-analysis-v2"
CASE_VERSION = "shared-holdout-public-case-feedback-confirmation-v2"
CASE_CANDIDATES = ("boolean", "case_details")


def _read(path, *, sealed=True):
    path = checked_path(path)
    require(path.is_file() and path.stat().st_size <= 32_000_000, "Bounded existing JSON input required")
    value = json.loads(path.read_text(encoding="utf-8"))
    return verify(value) if sealed else value


def _ratio(numerator, denominator):
    return {"numerator": numerator, "denominator": denominator,
            "value": numerator / denominator if denominator else None}


def _exposure_stats(pairs):
    counts, transitions = Counter(), Counter()
    for raw, conditional in pairs:
        a, b = raw["status"], conditional["status"]
        counts["unknown" if "unknown" in (a, b) else "tie" if a == b else
               "win" if b == "pass" else "loss"] += 1
        transitions[a + "->" + b] += 1
    aliases = {}
    for field in ("request_hash", "receipt_hash", "trajectory_hash"):
        available = [(a[field], b[field]) for a, b in pairs if field in a and field in b]
        aliases[field] = {"paired_references_available": len(available),
                          "same_reference_pairs": sum(a == b for a, b in available),
                          "missing_reference_pairs": len(pairs) - len(available)}
    return {
        "positions": len(pairs), "tasks": len({a["task_id"] for a, _ in pairs}),
        "declared_families": len({a["family_id"] for a, _ in pairs}),
        **{key: counts[key] for key in ("win", "loss", "tie", "unknown")},
        "direction": "conditional_vs_raw_within_same_history_task_repeat_condition",
        "transitions": dict(sorted(transitions.items())),
        "known_pair_coverage": _ratio(len(pairs) - counts["unknown"], len(pairs)),
        "raw_pass_to_conditional_fail": counts["loss"],
        "raw_pass_to_conditional_unknown": transitions["pass->unknown"],
        "raw": {"counts": {s: sum(a["status"] == s for a, _ in pairs) for s in ("pass", "fail", "unknown")},
                "missing": sum(a["missing"] for a, _ in pairs),
                "skill_injected": sum(a["skill_applied"] is True for a, _ in pairs)},
        "conditional": {"counts": {s: sum(b["status"] == s for _, b in pairs) for s in ("pass", "fail", "unknown")},
                        "missing": sum(b["missing"] for _, b in pairs),
                        "skill_injected": sum(b["skill_applied"] is True for _, b in pairs)},
        "all_attempt_delta": (sum(b["status"] == "pass" for _, b in pairs)
                              - sum(a["status"] == "pass" for a, _ in pairs)) / len(pairs) if pairs else None,
        "reference_aliases": aliases,
        "inferential_claim_authorized": False,
    }


def _raw_conditional(grid):
    positions = {(r["history"], r["task_id"], r["repeat"], r["condition"], r["exposure"]): r for r in grid}
    grouped = defaultdict(list)
    for row in grid:
        if row["exposure"] == "raw":
            key = row["history"], row["task_id"], row["repeat"], row["condition"], "conditional"
            require(key in positions, "Raw/conditional pairing is incomplete")
            grouped[row["condition"]].append((row, positions[key]))
    output = {}
    for condition, pairs in sorted(grouped.items()):
        entry = _exposure_stats(pairs)
        for field in ("region", "history"):
            entry["by_" + field] = {
                value: _exposure_stats([(a, b) for a, b in pairs if a[field] == value])
                for value in sorted({a[field] for a, _ in pairs})}
        output[condition] = entry
    return output


def _budget(accounting):
    fields = ("reserved_logical_requests", "terminal_logical_requests", "http_attempts", "terminal_failures",
              "terminal_reported_tokens", "retry_inclusive_token_usage_known", "by_kind", "request_limit",
              "temperature", "generation_seed_sent", "failed_attempt_token_usage_may_be_missing")
    require(type(accounting) is dict and set(fields) <= set(accounting), "Complete original request accounting required")
    by_kind = accounting["by_kind"]
    require(type(by_kind) is dict and all(type(k) is str and type(v) is int and v >= 0 for k, v in by_kind.items()),
            "Explicit nonnegative request-kind counts required")
    require(sum(by_kind.values()) == accounting["terminal_logical_requests"], "Request accounting counts disagree")
    return {key: accounting[key] for key in fields}


def _candidates(freeze, summary, protocol_hash, histories):
    require(freeze["record_hash"] == summary["freeze_hash"] and freeze["protocol_hash"] == protocol_hash
            and freeze["before_any_confirmation"] is True and set(freeze["histories"]) == histories,
            "Candidate freeze differs from completed run")
    proposal_origin = ("handwritten_fixture_proposal_not_real_learning"
                       if summary.get("provenance") == "engineering_fixture" else "real_model_unconfirmed_proposal")
    output, skills = {}, {}
    for history, frozen in sorted(freeze["histories"].items()):
        verify(frozen)
        require(frozen["history"] == history and frozen["protocol_hash"] == protocol_hash
                and frozen["update_statuses"] == summary["update_statuses"][history]
                and set(frozen["skills"]) == set(CONDITIONS), "History candidate metadata changed")
        output[history] = {"freeze_hash": frozen["record_hash"], "development_feedback_hash": frozen["feedback_hash"],
                           "conditions": {}}
        for condition, value in frozen["skills"].items():
            skill = RuleSkill.from_dict(value)
            skills[(history, condition)] = skill
            update_status = frozen["update_statuses"].get(condition)
            output[history]["conditions"][condition] = {
                "rule_skill_hash": skill.content_hash, "rule_count": len(skill.rules),
                "rules": [r.to_dict() for r in skill.rules], "update_status": update_status,
                "content_origin": proposal_origin if update_status == "candidate" else
                                  "frozen_parent_retained_not_new_learning",
                "semantic_support_verified": False, "deployment_authorized": False}
    return output, skills


def _case_candidates(freeze, summary, protocol_hash, histories):
    """Check the C freeze without opening B receipts or rerunning its parser."""
    require(freeze["record_hash"] == summary["freeze_hash"] and freeze["protocol_hash"] == protocol_hash
            and freeze["before_any_confirmation"] is True and freeze["selected_proposal_repeat"] == 0
            and freeze["noncandidate_retains_parent"] is True and freeze["deployment_authorized"] is False,
            "C candidate freeze or primary-repeat selection changed")
    for field in ("skills", "proposal_records", "update_statuses", "behavior_changed"):
        require(set(freeze[field]) == histories, "C freeze history roster changed")
    require(freeze["update_statuses"] == summary["update_statuses"]
            and freeze["behavior_changed"] == summary["behavior_changed"], "C update metadata changed")
    output, skills = {}, {}
    for history in sorted(histories):
        frozen = freeze["skills"][history]
        require(set(frozen) == {"no_skill", "current", *CASE_CANDIDATES}
                and all(set(freeze[field][history]) == set(CASE_CANDIDATES)
                        for field in ("proposal_records", "update_statuses", "behavior_changed")),
                "C candidate arm roster changed")
        typed = {condition: RuleSkill.from_dict(value) for condition, value in frozen.items()}
        parent = typed["no_skill"]
        require(not parent.rules and typed["current"] == parent, "C requires the same empty parent baseline")
        output[history] = {"freeze_hash": freeze["record_hash"], "selected_proposal_repeat": 0,
                           "proposal_record_hashes": {}, "conditions": {}}
        for condition, skill in typed.items():
            skills[(history, condition)] = skill
            status = freeze["update_statuses"][history].get(condition)
            if condition in CASE_CANDIDATES:
                proposal = verify(freeze["proposal_records"][history][condition])
                update = verify(proposal["update"])
                require(proposal["arm"] == condition and proposal["strategy"] == "mechanism"
                        and proposal["status"] == update["status"] == status
                        and status in {"candidate", "no_update", "invalid", "api_failure", "metadata_only", "scope_pending"}
                        and update["parent_hash"] == parent.content_hash
                        and proposal.get("deployment_authorized") is False
                        and proposal.get("semantic_support_verified") is False,
                        "C proposal differs from frozen parent, arm or status")
                expected = RuleSkill.from_dict(update["candidate"]) if status == "candidate" else parent
                changed = render_skill(skill) != render_skill(parent)
                require(skill == expected and type(freeze["behavior_changed"][history][condition]) is bool
                        and freeze["behavior_changed"][history][condition] == changed,
                        "C frozen content differs from selected proposal or declared behavior change")
                output[history]["proposal_record_hashes"][condition] = proposal["record_hash"]
            output[history]["conditions"][condition] = {
                "rule_skill_hash": skill.content_hash, "rule_count": len(skill.rules),
                "rules": [r.to_dict() for r in skill.rules], "update_status": status,
                "content_origin": (("handwritten_fixture_proposal_not_real_learning"
                    if summary["provenance"] == "engineering_fixture" else "real_model_unconfirmed_proposal")
                    if status == "candidate" else "frozen_parent_retained_not_new_learning"),
                "semantic_support_verified": False, "deployment_authorized": False}
    require(any(value for values in freeze["behavior_changed"].values() for value in values.values()),
            "All-empty C is not a completed behavioral confirmation")
    return output, skills


def analyze(root, sensitivity_plan):
    """Require completion first; recompute only immutable, predeclared views.

    Reads exactly summary, protocol, expected_positions, confirmation_rows and
    frozen_candidates, plus the supplied sensitivity plan (C also checks its
    frozen sensitivity_plan). Never reads API
    receipts, per-position audits, raw updater prompts or task answer material.
    """
    root = checked_path(root)
    summary = _read(root / "summary.json")
    require(summary.get("status") in {"completed_shadow_pilot", "completed_shadow_confirmation"},
            "Only a completed pilot or confirmation may be analyzed")
    is_case = summary["status"] == "completed_shadow_confirmation"
    candidates_names = CASE_CANDIDATES if is_case else ("local", "mechanism")
    conditions = ("no_skill", "current", *candidates_names)
    require(summary.get("provenance") in {"engineering_fixture", "real_model_synthetic_tasks"},
            "Explicit fixture or real-model synthetic provenance required")
    protocol = _read(root / "protocol.json")
    require(summary["protocol_hash"] == protocol["record_hash"], "Summary protocol binding mismatch")
    require(summary.get("deployment_authorized") is False and protocol.get("deployment_authorized") is False,
            "This analysis does not authorize deployment")
    if is_case:
        require(summary.get("version") == protocol.get("version") == CASE_VERSION
                and protocol.get("selection") == "repeat_0_only_no_best_of_n_selection"
                and protocol.get("no_A_solver_cache_reuse") is True
                and protocol.get("all_candidates_frozen_before_any_confirmation") is True
                and all(record.get("shared_holdout_exploratory_extension") is True
                        and record.get("independent_replication") is False for record in (summary, protocol)),
                "Unsupported C protocol, selection, baseline reuse or shared-holdout claim")
    roster_record = _read(root / "expected_positions.json")
    rows_record = _read(root / "confirmation_rows.json")
    require(set(roster_record) == {"positions", "record_hash"} and set(rows_record) == {"rows", "record_hash"},
            "Unexpected roster/row container fields")
    roster, rows = roster_record["positions"], rows_record["rows"]
    require(type(roster) is list and type(rows) is list, "Explicit frozen position lists required")
    if is_case:
        require(protocol.get("expected_positions_hash") == digest(roster), "C protocol roster hash changed")
    for row in rows:
        verify(row)
    original_metrics = verify(summary["metrics"])
    config = {"bootstrap_seed": original_metrics["bootstrap_seed"],
              "bootstrap_samples": original_metrics["bootstrap_samples"],
              **original_metrics["diagnostic_configuration"], "candidate_conditions": candidates_names}
    recomputed_metrics = summarize(rows, roster, **config)
    # v2 adds configurable candidate names but leaves the default local versus
    # mechanism measurements unchanged. Permit only this documented metadata
    # version difference; compare EVERY remaining field and retain the old table.
    metric_versions = {"mechanism-pilot-descriptive-metrics-v1", "mechanism-pilot-descriptive-metrics-v2"}
    require(original_metrics["version"] in metric_versions and recomputed_metrics["version"] in metric_versions,
            "Unsupported historical/default metrics compatibility")
    require(not is_case or original_metrics["version"] == "mechanism-pilot-descriptive-metrics-v2",
            "C requires explicit candidate-aware metrics v2")
    def comparable(metric):
        return {k: v for k, v in metric.items() if k not in {"version", "record_hash"}}
    require(comparable(recomputed_metrics) == comparable(original_metrics),
            "Sealed rows/roster do not reproduce original completed metrics")
    primary_metrics = original_metrics
    require(tuple(protocol["conditions"]) == conditions and tuple(protocol["exposures"]) == EXPOSURES,
            "Explicit four-condition two-exposure protocol required")
    histories = {f"h{i}" for i in range(protocol["histories"])}
    require({r["history"] for r in roster} == histories
            and {r["condition"] for r in roster} == set(conditions)
            and {r["exposure"] for r in roster} == set(EXPOSURES), "Protocol and roster arms differ")
    tasks = {r["task_id"] for r in roster}
    expected_keys = {(h, t, n, c, e) for h in histories for t in tasks for n in range(protocol["repeats"])
                     for c in conditions for e in EXPOSURES}
    require({(r["history"], r["task_id"], r["repeat"], r["condition"], r["exposure"]) for r in roster} == expected_keys,
            "Frozen roster is not the complete paired protocol grid")
    plan = _read(sensitivity_plan, sealed=False)
    require(type(plan) is dict and plan.get("kind") == "analysis_plan_not_experimental_result"
            and plan.get("original_protocol_unchanged") is True and plan.get("deployment_authorized") is False,
            "Explicit preregistered sensitivity-only plan required")
    excluded = plan.get("additional_sensitivity_excluded_task_ids")
    require(type(excluded) is list and all(type(t) is str for t in excluded) and len(excluded) == len(set(excluded)),
            "Explicit unique sensitivity task exclusions required")
    require(plan.get("primary_confirmation_tasks") == len(tasks) == 78
            and plan.get("sensitivity_confirmation_tasks") == 74 and len(excluded) == 4
            and set(excluded) <= tasks, "Sensitivity plan must identify exactly four of the original 78 tasks")
    if is_case:
        frozen_plan = _read(root / "sensitivity_plan.json")
        require(frozen_plan["record_hash"] == protocol.get("sensitivity_hash")
                and frozen_plan.get("plan") == plan
                and frozen_plan.get("plan_sha256") == hashlib.sha256(checked_path(sensitivity_plan).read_bytes()).hexdigest()
                and frozen_plan.get("additional_sensitivity_excluded_task_ids") == excluded
                and frozen_plan.get("main_panel_filtered") is False, "C frozen sensitivity plan changed")
    freeze = _read(root / "frozen_candidates.json")
    candidates, skills = (_case_candidates if is_case else _candidates)(freeze, summary, protocol["record_hash"], histories)
    for row in rows:
        skill = skills[(row["history"], row["condition"])]
        require(row.get("rule_skill_hash") == skill.content_hash, "Position uses a Skill outside the candidate freeze")
        require(not row["skill_applied"] or bool(skill.rules), "Empty Skill cannot be counted as injected")
        if is_case:
            require(row.get("update_status") == summary["update_statuses"][row["history"]].get(row["condition"])
                    and row.get("predeclared_near_duplicate") is (row["task_id"] in excluded),
                    "C row update status or sensitivity annotation changed")
    context = {"experiment": "C_public_case_feedback_confirmation" if is_case else "A_mechanism_learning_pilot",
        "candidate_conditions": list(candidates_names),
        "baseline_origin": "fresh_C_solver_calls_not_A_results" if is_case else "original_A_solver_calls",
        "shared_holdout_exploratory_extension": is_case,
        "independent_replication": False,
        "accounting_scope": "C_confirmation_only_excludes_A_B_and_aborted_runs" if is_case else
                            "A_development_updates_and_confirmation",
        "cross_run_scores_pooled": False, "cross_domain_evaluated": False}
    panels = {}
    for name, panel_rows, panel_roster, metrics in (
        ("primary_78", rows, roster, primary_metrics),
        ("sensitivity_74", [r for r in rows if r["task_id"] not in excluded],
         [r for r in roster if r["task_id"] not in excluded], None),
    ):
        metrics = metrics or summarize(panel_rows, panel_roster, **config)
        grid = _grid(panel_rows, panel_roster, conditions=conditions)
        panels[name] = {"tasks": len({r["task_id"] for r in panel_roster}),
            "comparison_context": context,
            "descriptive_metrics": metrics, "raw_vs_conditional": _raw_conditional(grid),
            "confirmation_reference_denominators": metrics["reference_reuse"],
            "reference_interpretation": "request_hash counts distinct initial request references only; receipt_hash "
                "counts selected-answer receipt references, not all revision calls. Aliases are not independent trials.",
            "subset_token_cost_reconstructed": False}
    return seal({"version": VERSION, "purpose": "read_only_completed_run_analysis_not_new_experiment",
        "source": {"summary_hash": summary["record_hash"], "protocol_hash": protocol["record_hash"],
                   "rows_hash": rows_record["record_hash"], "roster_hash": roster_record["record_hash"],
                   "freeze_hash": freeze["record_hash"], "sensitivity_plan_hash": digest(plan),
                   "original_metrics_version": original_metrics["version"],
                   "recomputed_metrics_version": recomputed_metrics["version"]},
        "model": {k: protocol.get("service", {}).get(k) for k in ("provider", "model", "reasoning_effort")},
        "experiment_context": context,
        "provenance": summary.get("provenance"), "candidate_content_and_source": candidates,
        "original_all_phase_accounting": _budget(summary["accounting"]),
        "sensitivity_excluded_task_ids": excluded, "panels": panels,
        "original_results_unchanged": True, "deployment_authorized": False,
        "limitations": ["The 78-task primary panel is retained; the 74-task view is sensitivity analysis only.",
            "Plan hashes bind content but cannot authenticate its declaration time; use the published pre-outcome plan.",
            "This analysis verifies summary/row/freeze consistency, not raw audit or execution authenticity.",
            "Known failures and unknowns remain distinct; repeats and aliases do not add independent tasks.",
            "Declared families and sensitivity exclusions do not prove semantic independence or cross-domain generalization.",
            "Rule injection is not proof that the solver followed its advice; an empty fallback is not learning.",
            ("C accounting includes only new confirmation calls; A, B and aborted-run costs must be reported separately."
             if is_case else "Original accounting includes all development, update and confirmation calls; subset costs are not inferred."),
            "C uses fresh baselines on the original shared holdout, not independent replication or pooled A/C evidence.",
            "No model, solver, Research, Skill update, new calibration or final evaluation is performed."]})


def _output_path(root, sensitivity_plan, output):
    """Validate before reading outcomes; reject source overlap and symlinks."""
    root, plan, output = (checked_path(path).resolve() for path in (root, sensitivity_plan, output))
    require(output != root and root not in output.parents and output not in root.parents,
            "Analysis export must be outside the analyzed run and its ancestor paths")
    require(output != plan and output not in plan.parents, "Analysis export cannot overwrite the sensitivity plan")
    require(output.suffix.lower() == ".json" and (not output.exists() or output.is_file()),
            "Analysis export requires a JSON file path")
    return output


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--sensitivity-plan", type=Path, required=True)
    parser.add_argument("--output", type=Path, help="Optional immutable JSON report outside the source run")
    args = parser.parse_args(argv)
    output = _output_path(args.run, args.sensitivity_plan, args.output) if args.output is not None else None
    result = analyze(args.run, args.sensitivity_plan)
    if output is not None:
        write_immutable_json(output, result)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
