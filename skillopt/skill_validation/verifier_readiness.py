"""Host-only evidence sufficiency and paired verifier diagnostics.

This is not a Verifier Gate. Even a fresh, sufficiently populated panel grants
no feedback, Skill, or deployment authority. H labels are descriptive audit
observations, not an oracle supplied to the probe generator. Only aggregate
statistics and hashes leave this function; never send this report to a model.
"""
from __future__ import annotations

import math
from collections import Counter, defaultdict

from skillopt.coevolution_v5.core import seal
from skillopt.validator_pilot.api import digest

from .models import PARTITIONS, hash_text, require, text

VERSION = "verifier-readiness-v1"
STATUSES = ("pass", "fail", "unknown")
DIRECTIONS = ("shared_correct", "shared_error", "repair", "regression", "unknown")
CONDITIONS = ("no_skill", "current", "candidate")
DEFAULT_CONFIG = {
    "min_independent_families": 16,
    "min_error_families": 4,
    "min_missed_error_families": 3,
    "min_correct_families": 8,
    "min_prediction_coverage": 0.9,
    "min_audit_coverage": 0.9,
}
_FIELDS = ("task_id", "family_id", "repeat", "condition", "audit_status", "fixed_status", "new_status")


def _ratio(numerator, denominator):
    return {"numerator": numerator, "denominator": denominator,
            "value": numerator / denominator if denominator else None}


def _support(rows):
    return {"positions": len(rows), "tasks": len({r["task_id"] for r in rows}),
            "families": len({r["family_id"] for r in rows})}


def _config(config):
    require(config is None or type(config) is dict and set(config) <= set(DEFAULT_CONFIG),
            "Only frozen readiness threshold fields are supported")
    value = {**DEFAULT_CONFIG, **(config or {})}
    for field, threshold in value.items():
        if field.endswith("coverage"):
            require(type(threshold) in {int, float} and math.isfinite(threshold) and 0 <= threshold <= 1,
                    "Finite coverage thresholds in [0, 1] required")
        else:
            require(type(threshold) is int and threshold >= 1, "Positive independent family minima required")
    return value


def _direction(before, after):
    if "unknown" in (before, after):
        return "unknown"
    if before == after:
        return "shared_correct" if after == "pass" else "shared_error"
    return "repair" if after == "pass" else "regression"


def _quality(rows, field):
    errors = [r for r in rows if r["audit_status"] == "fail"]
    correct = [r for r in rows if r["audit_status"] == "pass"]
    detected = [r for r in errors if r[field] == "fail"]
    false_reject = [r for r in correct if r[field] == "fail"]
    missed = [r for r in errors if r[field] != "fail"]
    counts = Counter(r[field] for r in rows)
    return {
        "statuses": {s: counts[s] for s in STATUSES},
        "coverage": _ratio(counts["pass"] + counts["fail"], len(rows)),
        "unknown": _ratio(counts["unknown"], len(rows)),
        "detected_errors": _support(detected), "false_rejections": _support(false_reject),
        "undetected_errors": _support(missed),
        "undetected_explicit_pass": _support([r for r in errors if r[field] == "pass"]),
        "undetected_unknown": _support([r for r in errors if r[field] == "unknown"]),
        "error_detection_position_rate": _ratio(len(detected), len(errors)),
        "false_rejection_position_rate": _ratio(len(false_reject), len(correct)),
        "error_families_with_any_detection": _ratio(_support(detected)["families"], _support(errors)["families"]),
        "correct_families_with_any_false_rejection": _ratio(_support(false_reject)["families"], _support(correct)["families"]),
    }


def _paired(rows):
    indexed = {(r["task_id"], r["repeat"], r["condition"]): r for r in rows}
    available = {r["condition"] for r in rows}
    summaries, unavailable = {}, {}
    for target, baseline in (("current", "no_skill"), ("candidate", "no_skill"), ("candidate", "current")):
        name = target + "_vs_" + baseline
        if not {target, baseline} <= available:
            unavailable[name] = sorted({target, baseline} - available)
            continue
        keys = sorted({(r["task_id"], r["repeat"]) for r in rows if r["condition"] in {target, baseline}})
        pairs = []
        for task, repeat in keys:
            before, after = indexed.get((task, repeat, baseline)), indexed.get((task, repeat, target))
            row = before or after
            pair = {"task_id": task, "family_id": row["family_id"],
                    "missing_baseline": before is None, "missing_target": after is None}
            for field in ("audit_status", "fixed_status", "new_status"):
                pair[field] = _direction(before[field] if before else "unknown", after[field] if after else "unknown")
            pairs.append(pair)
        summary = {"support": _support(pairs),
                   "missing_baseline_positions": sum(p["missing_baseline"] for p in pairs),
                   "missing_target_positions": sum(p["missing_target"] for p in pairs),
                   "audit_directions": {d: _support([p for p in pairs if p["audit_status"] == d]) for d in DIRECTIONS}}
        for field in ("fixed_status", "new_status"):
            table = Counter((p["audit_status"], p[field]) for p in pairs)
            cells = defaultdict(list)
            for pair in pairs:
                cells[pair["audit_status"], pair[field]].append(pair)
            regressions = [p for p in pairs if p["audit_status"] == "regression"]
            repairs = [p for p in pairs if p["audit_status"] == "repair"]
            correct_regression = [p for p in regressions if p[field] == "regression"]
            summary[field] = {
                "audit_vs_verifier": {h + "/" + v: table[h, v] for h in DIRECTIONS for v in DIRECTIONS},
                "audit_vs_verifier_distinct_tasks": {
                    h + "/" + v: _support(cells[h, v])["tasks"] for h in DIRECTIONS for v in DIRECTIONS},
                "audit_vs_verifier_distinct_families": {
                    h + "/" + v: _support(cells[h, v])["families"] for h in DIRECTIONS for v in DIRECTIONS},
                "audit_regressions": _support(regressions),
                "correctly_labeled_regressions": _support(correct_regression),
                "regression_detection_rate": _ratio(len(correct_regression), len(regressions)),
                "regressions_labeled_shared_correct": _support([p for p in regressions if p[field] == "shared_correct"]),
                "regressions_labeled_unknown": _support([p for p in regressions if p[field] == "unknown"]),
                "audit_repairs": _support(repairs),
                "correctly_labeled_repairs": _support([p for p in repairs if p[field] == "repair"]),
            }
        summaries[name] = summary
    return {"comparisons": summaries, "unavailable_comparisons_missing_conditions": unavailable}


def diagnose_readiness(records, *, protocol_hash, config=None, consumed_panels=None, partition=None):
    """Describe rows compatible with ``natural_verifier_replay.describe``.

    Extra fields are ignored via an explicit whitelist, not copied or stringified.
    ``partition`` can supply the partition for older rows lacking that field.
    Mixed panels are reported separately, never pooled to meet sample minima.
    ``consumed_panels=None`` conservatively declares every panel consumed. A
    caller must explicitly supply an empty list to declare new data. This is a
    declaration, not provenance authentication; upstream receipt checks remain
    necessary. Thresholds are pilot-budget requirements, not statistical power.
    """
    hash_text(protocol_hash)
    config = _config(config)
    require(type(records) in {list, tuple}, "Readiness requires a list or tuple of host records")
    require(partition is None or type(partition) is str and partition in PARTITIONS, "Unsupported declared partition")
    if consumed_panels is not None:
        require(type(consumed_panels) in {list, tuple, set, frozenset}, "Explicit consumed panel names required")
        require(all(type(p) is str and p in PARTITIONS for p in consumed_panels), "Unsupported consumed partition")
        require(len(consumed_panels) == len(set(consumed_panels)), "Duplicate consumed partition")
    rows, seen, identities, task_parts, family_parts = [], set(), {}, {}, defaultdict(set)
    for record in records:
        require(type(record) is dict and set(_FIELDS) <= set(record), "Task/family/repeat/condition/status row required")
        panel = record.get("partition", partition)
        require(type(panel) is str and panel in PARTITIONS, "Explicit supported partition required")
        require(partition is None or panel == partition, "Row differs from declared partition")
        row = {field: record[field] for field in _FIELDS}
        row["partition"] = panel
        for field in ("task_id", "family_id"):
            text(row[field], maximum=512)
        require(type(row["repeat"]) is int and row["repeat"] >= 0, "Nonnegative integer repeat required")
        require(type(row["condition"]) is str and row["condition"] in CONDITIONS, "Unknown Skill condition")
        for field in ("audit_status", "fixed_status", "new_status"):
            require(type(row[field]) is str and row[field] in STATUSES, "Only pass/fail/unknown statuses supported")
        task, family = row["task_id"], row["family_id"]
        require(task not in identities or identities[task] == family, "A task must retain its family identity")
        require(task not in task_parts or task_parts[task] == panel, "A task must belong to one partition")
        identities[task], task_parts[task] = family, panel
        family_parts[family].add(panel)
        key = panel, task, row["repeat"], row["condition"]
        require(key not in seen, "Duplicate task/repeat/condition position")
        seen.add(key)
        rows.append(row)
    rows.sort(key=lambda r: (r["partition"], r["task_id"], r["repeat"], r["condition"]))
    grouped = defaultdict(list)
    for row in rows:
        grouped[row["partition"]].append(row)
    if partition is not None:
        grouped.setdefault(partition, [])
    consumed = set(grouped) if consumed_panels is None else set(consumed_panels)
    panels = {}
    for panel, items in sorted(grouped.items()):
        errors = [r for r in items if r["audit_status"] == "fail"]
        correct = [r for r in items if r["audit_status"] == "pass"]
        missed = [r for r in errors if r["fixed_status"] != "fail"]
        newly_detected = [r for r in missed if r["new_status"] == "fail"]
        lost = [r for r in errors if r["fixed_status"] == "fail" and r["new_status"] != "fail"]
        counts = {"all": _support(items), "audit_errors": _support(errors), "audit_correct": _support(correct),
                  "audit_unknown": _support([r for r in items if r["audit_status"] == "unknown"]),
                  "fixed_undetected_errors": _support(missed)}
        fixed, new = _quality(items, "fixed_status"), _quality(items, "new_status")
        audit_coverage = _ratio(len(errors) + len(correct), len(items))
        shortages = [reason for observed, minimum, reason in (
            (counts["all"]["families"], config["min_independent_families"], "insufficient_independent_families"),
            (counts["audit_errors"]["families"], config["min_error_families"], "insufficient_error_families"),
            (counts["fixed_undetected_errors"]["families"], config["min_missed_error_families"], "insufficient_fixed_missed_error_families"),
            (counts["audit_correct"]["families"], config["min_correct_families"], "insufficient_correct_families"),
        ) if observed < minimum]
        for observed, minimum, reason in ((audit_coverage["value"], config["min_audit_coverage"], "insufficient_audit_coverage"),
                                         (new["coverage"]["value"], config["min_prediction_coverage"], "insufficient_prediction_coverage")):
            if observed is None or observed + 1e-12 < minimum:
                shortages.append(reason)
        overlaps = len({r["family_id"] for r in items if len(family_parts[r["family_id"]]) > 1})
        reasons = shortages + (["previously_consumed_panel"] if panel in consumed else [])
        if overlaps:
            reasons.append("family_overlap_across_partitions")
        if panel not in {"verifier_calibration", "verifier_audit"}:
            reasons.append("not_an_independent_verifier_panel")
        panels[panel] = {
            "status": "pending" if reasons else "ready_for_independent_calibration",
            "reasons": reasons, "evidence_sufficient": not shortages,
            "previously_consumed": panel in consumed, "cross_partition_family_count": overlaps,
            "counts": counts, "audit_coverage": audit_coverage, "fixed": fixed, "new": new,
            "new_detections": _support(newly_detected), "lost_detections": _support(lost),
            "paired_diagnostics": _paired(items),
            "records_hash": digest(items),
        }
    return seal({
        "version": VERSION, "purpose": "host_only_verifier_evidence_readiness_diagnostic",
        "host_only": True, "model_visible": False, "protocol_hash": protocol_hash,
        "config": config, "config_hash": digest(config), "records_hash": digest(rows), "panels": panels,
        "consumed_panels": sorted(consumed), "empty_input": not rows,
        "feedback_authorized": False, "skill_admission_authorized": False, "deployment_authorized": False,
        "limitations": [
            "Readiness is not verifier acceptance, feedback authority, or a deployment decision.",
            "Default minima are pilot-budget examples, not statistical sufficiency guarantees.",
            "Caller-declared families must already be deduplicated; family labels do not prove independence.",
            "Supports count distinct tasks/families with at least one matching position, not independent repeats.",
            "A family may contain correct and erroneous positions; category family counts are not additive.",
            "H is a frozen host audit, not absolute truth. Unknown is not a semantic failure.",
            "Undetected errors include unknown predictions, with explicit pass and unknown reported separately.",
            "Readiness does not bound false-rejection risk or certify paired regression detection.",
            "Hashes bind the supplied whitelist only; provenance and partition freshness require external verification.",
        ],
    })
