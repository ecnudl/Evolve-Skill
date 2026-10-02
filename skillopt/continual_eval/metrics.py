"""Descriptive, host-side measurements for a frozen five-benchmark stream.

These functions neither authenticate receipts nor authorize a Skill. A missing
run is not a zero score. An explicit terminal ``unknown`` contributes zero only
to the labelled all-attempt lower bound, never to confirmed semantic failures.
"""
from __future__ import annotations

import math
from collections import Counter

VERSION = "continual-evaluation-descriptive-metrics-v1"
STATUSES = ("pass", "fail", "unknown")
COST_FLAGS = frozenset({"usage_complete", "retry_inclusive_usage_known"})


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _name(value, label):
    _require(isinstance(value, str) and bool(value.strip()) and value == value.strip(),
             f"{label} must be a nonempty trimmed string")
    return value


def _number(value, label):
    _require(type(value) in (int, float) and math.isfinite(value) and value >= 0,
             f"{label} must be a finite nonnegative number")
    return value


def _ratio(numerator, denominator):
    return {"numerator": numerator, "denominator": denominator,
            "value": numerator / denominator if denominator else None}


def _aggregate_costs(rows):
    """Preserve unknown usage; booleans are completeness, not numeric spend."""
    numeric_fields = sorted({key for row in rows for key in row["costs"] if key not in COST_FLAGS})
    flag_fields = sorted({key for row in rows for key in row["costs"] if key in COST_FLAGS})
    totals, subtotals, unknown_positions = {}, {}, {}
    for field in numeric_fields:
        values = [row["costs"].get(field) for row in rows]
        unknown = sum(value is None for value in values)
        subtotal = sum(value for value in values if value is not None)
        totals[field] = None if unknown else subtotal
        subtotals[field] = subtotal
        unknown_positions[field] = unknown
    return {
        "costs": totals,
        "cost_known_subtotals": subtotals,
        "cost_unknown_positions": unknown_positions,
        "cost_completeness": {field: all(row["costs"].get(field) is True for row in rows)
                              for field in flag_fields},
    }


def _validate(plan, rows):
    _require(type(plan) is dict and type(rows) is list, "Expected a plan dictionary and a row list")
    order = plan.get("order")
    _require(type(order) is list and len(order) == 5, "Exactly five benchmark IDs required")
    for benchmark in order:
        _name(benchmark, "benchmark")
    _require(len(set(order)) == 5, "Duplicate benchmark in order")
    repeats = plan.get("repeats")
    _require(type(repeats) is int and repeats > 0, "Positive integer repeats required")
    _require(type(plan.get("tasks")) is list, "Frozen task roster required")
    tasks = {}
    for task in plan["tasks"]:
        _require(type(task) is dict, "Task must be a dictionary")
        for field in ("benchmark", "task_id", "family_id", "partition"):
            _name(task.get(field), field)
        _require(isinstance(task.get("project_id"), str), "Explicit project_id required (may be empty)")
        _require(task["benchmark"] in order, "Task benchmark outside frozen order")
        key = (task["benchmark"], task["task_id"])
        _require(key not in tasks, "Duplicate frozen task")
        tasks[key] = task
    checkpoints = {}
    _require(type(plan.get("checkpoints")) is list and plan["checkpoints"], "Frozen checkpoints required")
    for checkpoint in plan["checkpoints"]:
        _require(type(checkpoint) is dict, "Checkpoint must be a dictionary")
        for field in ("method", "history"):
            _name(checkpoint.get(field), field)
        _require("checkpoint_hash" in checkpoint, "Explicit checkpoint hash or null slot required")
        if checkpoint.get("checkpoint_hash") is not None:
            _name(checkpoint["checkpoint_hash"], "checkpoint_hash")
        stage = checkpoint.get("stage")
        _require(type(stage) is int and 0 <= stage <= 5, "Checkpoint stage must be 0..5")
        key = (checkpoint["method"], checkpoint["history"], stage)
        _require(key not in checkpoints, "Duplicate checkpoint identity")
        checkpoints[key] = checkpoint
    runs = sorted({key[:2] for key in checkpoints})
    _require(all({key[2] for key in checkpoints if key[:2] == run} == set(range(6)) for run in runs),
             "Every method/history requires explicit stages 0..5")
    observed = {}
    for row in rows:
        _require(type(row) is dict, "Observation must be a dictionary")
        for field in ("method", "history", "benchmark", "task_id", "family_id"):
            _name(row.get(field), field)
        stage, repeat = row.get("stage"), row.get("repeat")
        _require(type(stage) is int and 0 <= stage <= 5, "Observed stage must be 0..5")
        _require(type(repeat) is int and 0 <= repeat < repeats, "Repeat outside frozen range")
        checkpoint_key = (row["method"], row["history"], stage)
        _require(checkpoint_key in checkpoints, "Observation outside frozen checkpoint roster")
        _require(checkpoints[checkpoint_key].get("checkpoint_hash") is not None,
                 "Observation requires a registered checkpoint hash")
        task_key = (row["benchmark"], row["task_id"])
        _require(task_key in tasks, "Observation outside frozen task roster")
        task = tasks[task_key]
        _require(row["family_id"] == task["family_id"], "Observed family differs from frozen task")
        for field in ("partition", "project_id"):
            if field in row:
                _require(row[field] == task[field], f"Observed {field} differs from frozen task")
        if "checkpoint_hash" in row:
            _require(row["checkpoint_hash"] == checkpoints[checkpoint_key]["checkpoint_hash"],
                     "Observed checkpoint hash differs from frozen checkpoint")
        status, score = row.get("status"), row.get("score")
        _require(status in STATUSES, "Explicit pass/fail/unknown status required")
        if status == "unknown":
            _require(score is None, "Unknown must not claim an observed score")
        else:
            _number(score, "score")
            _require(score <= 1, "Score must be normalized to 0..1 by the frozen adapter")
        _require(isinstance(row.get("reason"), str), "Explicit reason string required")
        costs = row.get("costs")
        _require(type(costs) is dict, "Explicit cost dictionary required")
        for field, value in costs.items():
            _name(field, "cost field")
            if field in COST_FLAGS:
                _require(type(value) is bool, f"Cost completeness flag {field} must be boolean")
            elif value is not None:
                _number(value, f"cost {field}")
        if "prediction_hash" in row and row["prediction_hash"] is not None:
            _name(row["prediction_hash"], "prediction_hash")
        key = checkpoint_key + task_key + (repeat,)
        _require(key not in observed, "Duplicate observed position")
        observed[key] = row
    return order, repeats, tasks, checkpoints, runs, observed


def _cell(tasks, repeats, rows):
    expected = len(tasks) * repeats
    counts = Counter(row["status"] for row in rows)
    known = counts["pass"] + counts["fail"]
    total = sum(row["score"] for row in rows if row["status"] != "unknown")
    missing = expected - len(rows)
    return {
        "status": "pending" if missing or not tasks else "complete", "expected_positions": expected,
        "task_roster_available": bool(tasks),
        "observed_positions": len(rows), "missing_positions": missing,
        "tasks": len(tasks), "declared_families": len({task["family_id"] for task in tasks}),
        "repeats_per_task": repeats, "counts": {key: counts[key] for key in STATUSES},
        "score_sum_observed_known": total,
        # No completed-grid aggregate is emitted while positions are missing.
        "score_all_attempt_lower_bound": total / expected if not missing and expected else None,
        "score_all_attempt_upper_bound": (total + counts["unknown"]) / expected if not missing and expected else None,
        "score_evaluable": _ratio(total, known),
        "observed_attempt_lower_bound": _ratio(total, len(rows)),
        "completion_coverage": _ratio(len(rows), expected),
        "evaluable_coverage": _ratio(known, expected),
        "unknown_rate_observed": _ratio(counts["unknown"], len(rows)),
        **_aggregate_costs(rows),
    }


def _paired(run, stage, reference_stage, benchmark, tasks, repeats, observed, *, reference_run=None):
    reference_run = run if reference_run is None else reference_run
    counts = Counter()
    missing_candidate = missing_reference = missing_pairs = observed_unknown = 0
    known_delta = all_attempt_delta = 0.0
    for task in tasks:
        for repeat in range(repeats):
            tail = (benchmark, task["task_id"], repeat)
            candidate = observed.get(run + (stage,) + tail)
            reference = observed.get(reference_run + (reference_stage,) + tail)
            if candidate is not None and reference is not None:
                all_attempt_delta += (0 if candidate["status"] == "unknown" else candidate["score"])
                all_attempt_delta -= (0 if reference["status"] == "unknown" else reference["score"])
            missing_candidate += candidate is None
            missing_reference += reference is None
            if candidate is None or reference is None:
                counts["unknown"] += 1
                missing_pairs += 1
            elif "unknown" in (candidate["status"], reference["status"]):
                counts["unknown"] += 1
                observed_unknown += 1
            else:
                delta = candidate["score"] - reference["score"]
                counts["win" if delta > 0 else "loss" if delta < 0 else "tie"] += 1
                known_delta += delta
    expected = len(tasks) * repeats
    known = counts["win"] + counts["loss"] + counts["tie"]
    return {
        "benchmark": benchmark, "stage": stage, "reference_stage": reference_stage,
        "method": run[0], "history": run[1],
        "reference_method": reference_run[0], "reference_history": reference_run[1],
        "status": "pending" if missing_pairs or not tasks else "complete", "positions": expected,
        **{key: counts[key] for key in ("win", "loss", "tie", "unknown")},
        "missing_candidate_positions": missing_candidate, "missing_reference_positions": missing_reference,
        "missing_pairs": missing_pairs, "observed_unknown_pairs": observed_unknown,
        "known_pair_coverage": _ratio(known, expected), "known_pair_mean_delta": _ratio(known_delta, known),
        "native_mean_delta_all_attempt_lower_bound": (
            all_attempt_delta / expected if expected and not missing_pairs else None),
        "tasks": len(tasks), "declared_families": len({task["family_id"] for task in tasks}),
        "repeats_per_task": repeats,
    }


def _cross_method(run, reference_method, *, reference_stage, runs, order, tasks, repeats, observed):
    reference_run = (reference_method, run[1])
    if reference_run not in runs:
        return {"status": "pending", "reference_registered": False,
                "reference_method": reference_method, "reference_history": run[1],
                "reason": "No reference method registered for this same history; no substitute baseline inferred",
                "by_stage": []}
    stages = []
    for stage in range(6):
        ref_stage = stage if reference_stage == "same_stage" else reference_stage
        pairs = [_paired(run, stage, ref_stage, benchmark, tasks[benchmark], repeats, observed,
                         reference_run=reference_run) for benchmark in order]
        deltas = [pair["native_mean_delta_all_attempt_lower_bound"] for pair in pairs]
        complete = all(delta is not None for delta in deltas)
        stages.append({
            "stage": stage, "reference_stage": ref_stage, "status": "complete" if complete else "pending",
            "pairs": pairs,
            "macro_native_mean_delta_all_attempt_lower_bound": sum(deltas) / 5 if complete else None,
            "worst_domain_native_mean_delta_all_attempt_lower_bound": min(deltas) if complete else None,
            "negative_domain_count": sum(delta < 0 for delta in deltas) if complete else None,
        })
    return {"status": "complete" if all(stage["status"] == "complete" for stage in stages) else "pending",
            "reference_registered": True, "reference_method": reference_method,
            "reference_history": run[1], "by_stage": stages}


def _transfer(components):
    complete = all(row["delta"] is not None for row in components)
    return {"status": "complete" if complete else "pending", "components": components,
            "value": sum(row["delta"] for row in components) / len(components) if complete else None}


def summarize(plan: dict, rows: list[dict]) -> dict:
    """Summarize terminal observations without imputing unperformed runs.

    ``plan.tasks`` is the frozen evaluation roster, not development examples.
    Scores must already follow each adapter's frozen normalization in [0, 1].
    Costs are flat nullable numeric counters plus explicit completeness flags;
    callers must avoid double-counting shared cached calls. Six checkpoint slots
    are required per method/history; absent
    hashes represent unregistered slots, which cannot have observations. Missing
    benchmark panels remain pending, never empty perfect-score panels. No
    statistical significance is claimed.
    """
    order, repeats, tasks, checkpoints, runs, observed = _validate(plan, rows)
    by_benchmark = {benchmark: [task for (name, _), task in tasks.items() if name == benchmark]
                    for benchmark in order}
    reports = []
    for run in runs:
        matrix, stage_metrics = {}, []
        paired = {"vs_stage0": [], "vs_previous": []}
        for stage in range(6):
            cells = {}
            for benchmark in order:
                selected = [observed[run + (stage, benchmark, task["task_id"], repeat)]
                            for task in by_benchmark[benchmark] for repeat in range(repeats)
                            if run + (stage, benchmark, task["task_id"], repeat) in observed]
                cells[benchmark] = _cell(by_benchmark[benchmark], repeats, selected)
                if stage:
                    for key, reference_stage in (("vs_stage0", 0), ("vs_previous", stage - 1)):
                        paired[key].append(_paired(run, stage, reference_stage, benchmark,
                                                   by_benchmark[benchmark], repeats, observed))
            matrix[str(stage)] = cells
            complete = all(cell["status"] == "complete" for cell in cells.values())
            deltas = {}
            for benchmark in order:
                current = cells[benchmark]["score_all_attempt_lower_bound"]
                baseline = matrix["0"][benchmark]["score_all_attempt_lower_bound"]
                deltas[benchmark] = current - baseline if current is not None and baseline is not None else None
            delta_complete = all(value is not None for value in deltas.values())
            stage_metrics.append({
                "stage": stage, "status": "complete" if complete else "pending",
                "checkpoint_hash": checkpoints[run + (stage,)]["checkpoint_hash"],
                "macro_score_all_attempt_lower_bound": (
                    sum(cell["score_all_attempt_lower_bound"] for cell in cells.values()) / 5 if complete else None),
                "delta_vs_stage0": deltas,
                "delta_status": "complete" if delta_complete else "pending",
                "macro_delta_vs_stage0": sum(deltas.values()) / 5 if delta_complete else None,
                "worst_domain_delta_vs_stage0": min(deltas.values()) if delta_complete else None,
                "negative_domain_count_vs_stage0": sum(value < 0 for value in deltas.values()) if delta_complete else None,
            })

        def component(benchmark, stage, reference_stage):
            score = matrix[str(stage)][benchmark]["score_all_attempt_lower_bound"]
            reference = matrix[str(reference_stage)][benchmark]["score_all_attempt_lower_bound"]
            return {"benchmark": benchmark, "stage": stage, "reference_stage": reference_stage,
                    "delta": score - reference if score is not None and reference is not None else None}

        cross_method = {
            "vs_no_skill_stage0": _cross_method(
                run, "no_skill", reference_stage=0, runs=runs, order=order, tasks=by_benchmark,
                repeats=repeats, observed=observed),
        }
        if ("skillopt", run[1]) in runs:
            cross_method["vs_skillopt_same_stage"] = _cross_method(
                run, "skillopt", reference_stage="same_stage", runs=runs, order=order,
                tasks=by_benchmark, repeats=repeats, observed=observed)
        reports.append({
            "method": run[0], "history": run[1], "matrix": matrix, "stage_metrics": stage_metrics,
            "forward_transfer": _transfer([component(benchmark, index, 0)
                                             for index, benchmark in enumerate(order) if index]),
            "backward_transfer": _transfer([component(benchmark, 5, index + 1)
                                              for index, benchmark in enumerate(order[:-1])]),
            "pairs": paired, "cross_method_pairs": cross_method,
        })
    expected = len(checkpoints) * len(tasks) * repeats
    complete = len(rows) == expected and {key[0] for key in tasks} == set(order)
    return {
        "version": VERSION, "status": "complete" if complete else "pending",
        "order": list(order), "runs": reports, "expected_positions": expected,
        "observed_positions": len(rows), "missing_positions": expected - len(rows),
        "tasks": len(tasks), "declared_families": len({(key[0], task["family_id"]) for key, task in tasks.items()}),
        "repeats_per_task": repeats, **_aggregate_costs(rows),
        "unavailable_benchmarks": [benchmark for benchmark in order if not by_benchmark[benchmark]],
        "limitations": {
            "descriptive_only": True, "statistical_significance_claimed": False,
            "family_independence_certified": False, "skill_or_verifier_authorized": False,
            "baseline": "stage0 of the same method/history; not necessarily No-Skill unless declared in protocol",
            "cross_method_comparisons": "same-history no_skill stage0 and, when registered, same-history same-stage skillopt; no substitute history inferred",
            "unknown": "terminal unknown scores bound zero to one; never counted as confirmed fail",
            "delta_basis": "difference of descriptive all-attempt lower-bound scores, not a bound on semantic effect",
            "missing": "unperformed runs remain missing; incomplete cells and required aggregates are pending",
            "forward_transfer": "mean immediately-before-first-learning minus stage0 on benchmarks 2..5",
            "backward_transfer": "mean stage5 minus immediately-after-first-learning on benchmarks 1..4",
            "costs": "sum supplied counters; null/missing usage stays unknown, completeness flags AND separately; no claim of de-aliased actual API cost",
        },
    }
