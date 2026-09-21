"""Host-only finite calibration and descriptive natural-output measurements.

Input receipts are verified by the caller. Hashes here bind the supplied rows,
policy, protocol and manifest; they do not authenticate execution or provenance.
No files, model, reference program, probe answers or deployment API are used.
"""
from __future__ import annotations

import math
import random
from collections import Counter, defaultdict
from copy import deepcopy

from skillopt.coevolution_v5.core import seal
from skillopt.validator_pilot.api import digest

from .models import hash_text, require, text

VERSION = "natural-coding-metrics-v1"
STATUSES = ("pass", "fail", "unknown")
DEFAULT_CONFIG = {
    "min_independent_families": 8,
    "min_natural_errors": 4,
    "min_natural_correct": 12,
    "min_coverage": 0.9,
    "max_false_rejection_increase": 0.0,
    "min_net_new_detection": 1,
}
_CALIBRATION_FIELDS = {
    "task_id", "family_id", "repeat", "condition", "audit_status", "fixed_status", "new_status",
    "artifact_hash", "report_hash", "audit_hash", "partition",
}


def _ratio(numerator, denominator):
    return {"numerator": numerator, "denominator": denominator,
            "value": numerator / denominator if denominator else None}


def _config(config):
    require(config is None or type(config) is dict and set(config) <= set(DEFAULT_CONFIG),
            "Only preregistered calibration threshold fields are supported")
    value = {**DEFAULT_CONFIG, **(config or {})}
    for key in ("min_independent_families", "min_natural_errors", "min_natural_correct", "min_net_new_detection"):
        require(type(value[key]) is int and value[key] >= 1, "Positive frozen family/sample/gain minima required")
    for key in ("min_coverage", "max_false_rejection_increase"):
        require(type(value[key]) in {int, float} and math.isfinite(value[key]) and 0 <= value[key] <= 1,
                "Finite risk/coverage thresholds in [0, 1] required")
    return value


def _identity(row, families):
    for key in ("task_id", "family_id"):
        text(row[key], maximum=512)
    require(type(row["repeat"]) is int and row["repeat"] >= 0, "Nonnegative integer repeat required")
    task, family = row["task_id"], row["family_id"]
    require(task not in families or families[task] == family, "A task must retain its frozen family identity")
    families[task] = family


def _calibration_summary(rows, field):
    errors = [row for row in rows if row["audit_status"] == "fail"]
    correct = [row for row in rows if row["audit_status"] == "pass"]
    counts = Counter(row[field] for row in rows)
    return {
        "statuses": {status: counts[status] for status in STATUSES},
        "coverage": _ratio(counts["pass"] + counts["fail"], len(rows)),
        "error_detection": _ratio(sum(row[field] == "fail" for row in errors), len(errors)),
        "false_rejection": _ratio(sum(row[field] == "fail" for row in correct), len(correct)),
        "unknown": _ratio(counts["unknown"], len(rows)),
    }


def calibrate_policy(records, *, policy_hash, protocol_hash, manifest_hash, config=None):
    """Finite permission for qualified Coding development feedback, never a Skill.

    Each row is one requested-behavior obligation for one artifact position.
    Fixed/new statuses share precisely the same rows and H denominators; adding
    probes cannot add denominator units. ``new_status=fail`` is a verifier
    prediction, not independently established truth. H is consumed only by this
    host decision and is never used to fill in a probe's expected answer.
    """
    for value in (policy_hash, protocol_hash, manifest_hash):
        hash_text(value)
    config = _config(config)
    rows, families, seen = [], {}, set()
    bindings = {"policy_hash": policy_hash, "protocol_hash": protocol_hash, "manifest_hash": manifest_hash}
    for record in records:
        require(type(record) is dict and _CALIBRATION_FIELDS <= set(record)
                and set(record) <= _CALIBRATION_FIELDS | set(bindings),
                "Exact artifact/task/obligation calibration row required")
        require(all(record[key] == value for key, value in bindings.items() if key in record),
                "Calibration row differs from its frozen policy/protocol/manifest")
        _identity(record, families)
        require(record["partition"] == "verifier_calibration", "Only independent verifier_calibration rows allowed")
        require(record["condition"] in {"no_skill", "current"}, "Only frozen No-Skill/Current artifacts allowed")
        for field in ("audit_status", "fixed_status", "new_status"):
            require(record[field] in STATUSES, "Calibration requires pass/fail/unknown statuses")
        for field in ("artifact_hash", "report_hash", "audit_hash"):
            hash_text(record[field])
        key = record["task_id"], record["repeat"], record["condition"]
        require(key not in seen, "Duplicate calibration task/repeat/condition position")
        seen.add(key)
        rows.append(deepcopy(record))
    rows.sort(key=lambda row: (row["task_id"], row["repeat"], row["condition"]))
    fixed, new = (_calibration_summary(rows, field) for field in ("fixed_status", "new_status"))
    errors = [row for row in rows if row["audit_status"] == "fail"]
    correct = [row for row in rows if row["audit_status"] == "pass"]
    newly_detected = sum(row["fixed_status"] != "fail" and row["new_status"] == "fail" for row in errors)
    lost_detection = sum(row["fixed_status"] == "fail" and row["new_status"] != "fail" for row in errors)
    net_new = newly_detected - lost_detection
    false_rejection_increase = (new["false_rejection"]["value"] - fixed["false_rejection"]["value"]
                                if correct else None)
    insufficient = [reason for observed, minimum, reason in (
        (len(set(families.values())), config["min_independent_families"], "insufficient_independent_families"),
        (len(errors), config["min_natural_errors"], "insufficient_natural_errors"),
        (len(correct), config["min_natural_correct"], "insufficient_natural_correct"),
    ) if observed < minimum]
    risks = []
    if new["coverage"]["value"] is None or new["coverage"]["value"] + 1e-12 < config["min_coverage"]:
        risks.append("coverage_below_frozen_floor")
    if false_rejection_increase is None or false_rejection_increase > config["max_false_rejection_increase"] + 1e-12:
        risks.append("false_rejection_risk_increased_or_unknown")
    if net_new < config["min_net_new_detection"]:
        risks.append("insufficient_net_new_detection")
    status = "pending" if insufficient else "rejected" if risks else "accepted"
    return seal({
        "version": VERSION, "purpose": "finite_verifier_policy_calibration", "status": status,
        "reasons": insufficient or risks or ["passed_preregistered_finite_calibration_constraints"],
        "insufficient_evidence": insufficient, "risk_findings": risks,
        "policy_hash": policy_hash, "protocol_hash": protocol_hash, "manifest_hash": manifest_hash,
        "config": config, "config_hash": digest(config), "records_hash": digest(rows),
        "unit": "one requested_behavior obligation per task/repeat/condition artifact position, not per probe",
        "counts": {"artifact_obligation_positions": len(rows), "tasks": len(families),
                   "independent_families": len(set(families.values())), "natural_errors": len(errors),
                   "natural_correct": len(correct), "audit_unknown": len(rows) - len(errors) - len(correct),
                   "error_families": len({row["family_id"] for row in errors}),
                   "correct_families": len({row["family_id"] for row in correct})},
        "fixed": fixed, "new": new, "new_detection_count": newly_detected,
        "lost_detection_count": lost_detection, "net_new_detection": net_new,
        "false_rejection_increase": false_rejection_increase,
        "qualified_development_feedback_authorized": status == "accepted",
        "scope": {"adapter_domain": "coding", "obligation_kinds": ["requested_behavior"],
                  "allowed_partition": "development", "purpose": "qualified_public_feedback_only"},
        "deployment_authorized": False, "skill_admission_authorized": False,
        "cross_domain_authorized": False, "near_miss_authorized": False,
        "limitations": [
            "A probe mismatch is a proposed verifier failure judgment, not audit truth or a supplied answer.",
            "Unknown audit/prediction statuses are not semantic failures; absent errors leave calibration Pending.",
            "Hashes bind caller-verified rows and frozen declarations; they do not authenticate provenance or freeze timing.",
            "Finite development-feedback permission is not general verifier admission, a Skill approval, or a safety guarantee.",
            "No Near-Miss or cross-domain scope is calibrated by this requested-behavior panel.",
        ],
    })


def _percentile(values, probability):
    position = (len(values) - 1) * probability
    low, high = math.floor(position), math.ceil(position)
    return values[low] + (values[high] - values[low]) * (position - low)


def _estimate(observations, families, *, seed, samples, label):
    """Average repeats inside each task, then resample complete family clusters."""
    tasks = {task: sum(values) / len(values) for task, values in sorted(observations.items())}
    clusters = defaultdict(list)
    for task, value in tasks.items():
        clusters[families[task]].append(value)
    groups = [clusters[key] for key in sorted(clusters)]
    point = sum(tasks.values()) / len(tasks) if tasks else None
    lower = upper = None
    if groups:
        rng = random.Random(int(digest([seed, label]), 16))
        draws = []
        for _ in range(samples):
            selected = [groups[rng.randrange(len(groups))] for _ in groups]
            draws.append(sum(sum(group) for group in selected) / sum(len(group) for group in selected))
        draws.sort()
        lower, upper = _percentile(draws, 0.025), _percentile(draws, 0.975)
    return {
        "estimate": point, "lower": lower, "upper": upper, "confidence": 0.95,
        "method": "descriptive percentile family-cluster bootstrap of task means after averaging repeats",
        "weighting": "equal task weight; all tasks of a sampled family move together",
        "protocolseed": seed, "bootstrap_samples": samples, "task_count": len(tasks),
        "family_count": len(groups), "per_task_repeat_mean": tasks,
        "inferential_claim_authorized": False,
    }


def summarize(records, *, partition="final", protocolseed=0, bootstrap_samples=2000):
    """Describe one explicit partition; repeats are not independent.

    ``status`` is the caller's stronger host audit; ``native_status`` is the base
    native-test result. Unknown remains separate from fail. It contributes zero
    successes only in explicitly labeled full-attempt pass rates and deltas.
    Missing positions in a compared arm are retained as unknown pairs.
    """
    require(partition in {"development", "skill_confirmation", "final"}, "Unsupported descriptive partition")
    require(type(protocolseed) is int and protocolseed >= 0, "Nonnegative integer protocolseed required")
    require(type(bootstrap_samples) is int and 1 <= bootstrap_samples <= 100000,
            "Bounded positive integer bootstrap sample count required")
    required = {"task_id", "family_id", "repeat", "arm", "status", "native_status"}
    rows, families, indexed = [], {}, {}
    for record in records:
        require(type(record) is dict and required <= set(record), "Final task/family/repeat/arm/status row required")
        require("partition" not in record or record["partition"] == partition,
                "Only rows matching the declared partition can enter a summary")
        _identity(record, families)
        text(record["arm"], maximum=128)
        require(record["status"] in STATUSES and record["native_status"] in STATUSES,
                "Final results require pass/fail/unknown statuses")
        row = {key: deepcopy(record[key]) for key in sorted(required)}
        key = row["task_id"], row["repeat"], row["arm"]
        require(key not in indexed, "Duplicate final task/repeat/arm position")
        indexed[key] = row
        rows.append(row)
    rows.sort(key=lambda row: (row["task_id"], row["repeat"], row["arm"]))
    grouped = defaultdict(list)
    for row in rows:
        grouped[row["arm"]].append(row)
    estimates = {"seed": protocolseed, "samples": bootstrap_samples}
    arms = {}
    for arm, group in sorted(grouped.items()):
        counts, native = Counter(row["status"] for row in group), Counter(row["native_status"] for row in group)
        successes, native_gap = defaultdict(list), defaultdict(list)
        for row in group:
            successes[row["task_id"]].append(int(row["status"] == "pass"))
            native_gap[row["task_id"]].append(int(row["native_status"] == "pass") - int(row["status"] == "pass"))
        arms[arm] = {
            "attempts": len(group), "tasks": len(successes),
            "families": len({row["family_id"] for row in group}),
            "counts": {status: counts[status] for status in STATUSES},
            "full_attempt_success": _ratio(counts["pass"], len(group)),
            "known_audit_coverage": _ratio(counts["pass"] + counts["fail"], len(group)),
            "native_counts": {status: native[status] for status in STATUSES},
            "native_full_attempt_success": _ratio(native["pass"], len(group)),
            "native_vs_stronger": {
                "native_pass_stronger_fail": sum(row["native_status"] == "pass" and row["status"] == "fail" for row in group),
                "native_fail_stronger_pass": sum(row["native_status"] == "fail" and row["status"] == "pass" for row in group),
                "unknown_pairs": sum("unknown" in (row["native_status"], row["status"]) for row in group),
                "full_attempt_success_gap": (native["pass"] - counts["pass"]) / len(group),
                "task_mean_gap_ci": _estimate(native_gap, families, label=arm + ":native-minus-stronger", **estimates),
            },
            "task_mean_success_ci": _estimate(successes, families, label=arm + ":success", **estimates),
        }
    pairs = {}
    for arm in sorted(grouped):
        for baseline in ("no_skill", "current"):
            if arm == baseline or baseline not in grouped:
                continue
            positions = sorted({(row["task_id"], row["repeat"]) for row in grouped[arm] + grouped[baseline]})
            counts, effects, missing = Counter(), defaultdict(list), Counter()
            for task, repeat in positions:
                left, right = indexed.get((task, repeat, baseline)), indexed.get((task, repeat, arm))
                before, after = (left["status"] if left else "unknown"), (right["status"] if right else "unknown")
                missing["baseline"] += left is None
                missing["arm"] += right is None
                outcome = ("unknown" if "unknown" in (before, after) else "tie" if before == after
                           else "win" if after == "pass" else "loss")
                counts[outcome] += 1
                effects[task].append(int(after == "pass") - int(before == "pass"))
            pairs[arm + "_vs_" + baseline] = {
                "arm": arm, "baseline": baseline, "positions": len(positions),
                **{outcome: counts[outcome] for outcome in ("win", "loss", "tie", "unknown")},
                "missing_baseline_positions": missing["baseline"], "missing_arm_positions": missing["arm"],
                "known_pair_coverage": _ratio(len(positions) - counts["unknown"], len(positions)),
                "task_mean_full_attempt_delta_ci": _estimate(effects, families, label=arm + ":vs:" + baseline, **estimates),
            }
    return seal({
        "version": VERSION, "purpose": "descriptive_" + partition + "_audit_summary", "partition": partition,
        "records_hash": digest(rows),
        "protocolseed": protocolseed, "bootstrap_samples": bootstrap_samples,
        "attempts": len(rows), "tasks": len(families), "families": len(set(families.values())),
        "arms": arms, "paired": pairs, "deployment_authorized": False,
        "limitations": [
            "Native and stronger host audits are finite checks, not full semantic correctness.",
            "Unknown is not fail; it is only an unsuccessful attempt in full-attempt success numerators.",
            "Paired observations and descriptive confidence intervals do not establish causal Skill effects.",
            "Repeats are averaged within each task; bootstrap sampling moves complete declared families together.",
            "Family definitions, missing attempts and small family counts limit interpretation; no generalization claim is authorized.",
        ],
    })
