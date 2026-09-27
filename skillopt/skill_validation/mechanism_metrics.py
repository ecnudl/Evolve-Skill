"""Host-only, descriptive mechanism-pilot measurements on a frozen position grid.

The caller verifies receipts and supplies audit statuses. These measurements do
not authenticate evidence, certify family independence, or authorize a Skill.
Unknown contributes no success to *all-attempt* rates but is never a known fail.
"""
from __future__ import annotations

import math
import random
import re
from collections import Counter, defaultdict

from skillopt.coevolution_v5.core import seal
from skillopt.validator_pilot.api import digest

from .models import hash_text, require, text

VERSION = "mechanism-pilot-descriptive-metrics-v2"
CONDITIONS = ("no_skill", "current", "local", "mechanism")
EXPOSURES = ("raw", "conditional")
REGIONS = ("target_related", "near_miss", "boundary_control", "unrelated")
STATUSES = ("pass", "fail", "unknown")
IDENTITY = ("history", "task_id", "family_id", "domain", "region", "repeat", "condition", "exposure")
KEY = ("history", "task_id", "repeat", "condition", "exposure")


def _ratio(n, d):
    return {"numerator": n, "denominator": d, "value": n / d if d else None}


def _key(row):
    return tuple(row[field] for field in KEY)


def _identity(record, *, conditions=CONDITIONS):
    require(type(record) is dict and set(IDENTITY) <= set(record), "Complete frozen position identity required")
    for field in ("history", "task_id", "family_id", "domain"):
        text(record[field], maximum=512)
    require(type(record["repeat"]) is int and record["repeat"] >= 0, "Nonnegative integer repeat required")
    require(record["condition"] in conditions, "Unsupported condition")
    require(record["exposure"] in EXPOSURES, "Unsupported exposure")
    require(record["region"] in REGIONS, "Unsupported region")
    return {field: record[field] for field in IDENTITY}


def _grid(records, expected_positions, *, conditions=CONDITIONS):
    expected, metadata, rosters = {}, {}, defaultdict(dict)
    for record in expected_positions:
        row = _identity(record, conditions=conditions)
        key = _key(row)
        require(key not in expected, "Duplicate expected position")
        expected[key] = row
        task_metadata = tuple(row[field] for field in ("family_id", "domain", "region"))
        require(row["task_id"] not in metadata or metadata[row["task_id"]] == task_metadata,
                "Task family/domain/region changed across positions")
        metadata[row["task_id"]] = task_metadata
        roster = rosters[row["exposure"]].setdefault(row["condition"], set())
        roster.add((row["history"], row["task_id"], row["repeat"]))
    for arms in rosters.values():
        require("no_skill" in arms and "current" in arms, "Manifest must include explicit Base and Current")
        require(all(roster == arms["no_skill"] for roster in arms.values()),
                "Conditions must share the same frozen position roster within each exposure")
    observed = {}
    for record in records:
        row = _identity(record, conditions=conditions)
        key = _key(row)
        require(key not in observed, "Duplicate observed position")
        require(key in expected, "Observed position is outside frozen manifest")
        require(row == expected[key], "Observed metadata differs from frozen position")
        require(record.get("status") in STATUSES, "Explicit pass/fail/unknown status required")
        require(type(record.get("skill_applied")) is bool, "Explicit boolean skill_applied required")
        require(row["condition"] != "no_skill" or not record["skill_applied"],
                "No-Skill cannot have a Skill applied")
        row.update(status=record["status"], skill_applied=record["skill_applied"], missing=False)
        # Only these optional identity references enter the summary. Arbitrary
        # cost payloads, prompts, code, or hidden answers are not serialized.
        for field in ("request_hash", "receipt_hash", "trajectory_hash"):
            if field in record:
                hash_text(record[field])
                row[field] = record[field]
        observed[key] = row
    rows = []
    for key in sorted(expected):
        rows.append(observed.get(key, {**expected[key], "status": "unknown", "skill_applied": None,
                                      "missing": True}))
    return rows


def _arm(rows):
    counts = Counter(row["status"] for row in rows)
    references = {}
    for field in ("request_hash", "receipt_hash", "trajectory_hash"):
        available = [row[field] for row in rows if field in row]
        references[field] = {"referenced_positions": len(available), "unique_references": len(set(available)),
                             "aliased_positions": len(available) - len(set(available))}
    applied = sum(row["skill_applied"] is True for row in rows)
    not_applied = sum(row["skill_applied"] is False for row in rows)
    conditional_skill = bool(rows) and rows[0]["condition"] != "no_skill" and rows[0]["exposure"] == "conditional"
    return {
        "positions": len(rows), "tasks": len({row["task_id"] for row in rows}),
        "declared_families": len({row["family_id"] for row in rows}),
        "histories": len({row["history"] for row in rows}),
        "counts": {status: counts[status] for status in STATUSES},
        "missing_positions": sum(row["missing"] for row in rows),
        "all_attempt_success": _ratio(counts["pass"], len(rows)),
        "known_coverage": _ratio(counts["pass"] + counts["fail"], len(rows)),
        "skill_application_coverage": _ratio(applied, len(rows)),
        "skill_not_applied_positions": not_applied,
        "application_unknown_positions": len(rows) - applied - not_applied,
        "fallback_or_empty_positions": not_applied if conditional_skill else None,
        "fallback_or_empty_rate": _ratio(not_applied, len(rows)) if conditional_skill else None,
        "no_applied_skill_observed": applied == 0,
        "reference_reuse": references,
        "learning_gain_established": False,
    }


def _percentile(values, p):
    index = (len(values) - 1) * p
    lo, hi = math.floor(index), math.ceil(index)
    return values[lo] + (values[hi] - values[lo]) * (index - lo)


def _cluster_delta(pairs, *, seed, samples):
    # Repeats -> history/task -> task -> family. All observed histories stay
    # together when a family is sampled; this does not quantify learning-path
    # uncertainty or turn multiple histories into extra task families.
    repeats, histories, families = defaultdict(list), defaultdict(list), defaultdict(list)
    task_families = {}
    for candidate, baseline in pairs:
        repeats[(candidate["history"], candidate["task_id"])].append(
            int(candidate["status"] == "pass") - int(baseline["status"] == "pass"))
        task_families[candidate["task_id"]] = candidate["family_id"]
    for (_, task), values in repeats.items():
        histories[task].append(sum(values) / len(values))
    for task, values in histories.items():
        families[task_families[task]].append(sum(values) / len(values))
    means = {family: sum(values) / len(values) for family, values in sorted(families.items())}
    values = list(means.values())
    lower = upper = estimate = None
    if values:
        estimate = sum(values) / len(values)
        rng = random.Random(int(digest([seed, sorted((a["history"], a["task_id"], a["repeat"],
                                                    a["condition"], b["condition"], a["exposure"])
                                                   for a, b in pairs)]), 16))
        draws = sorted(sum(values[rng.randrange(len(values))] for _ in values) / len(values)
                       for _ in range(samples))
        lower, upper = _percentile(draws, .025), _percentile(draws, .975)
    return {
        "estimate": estimate, "lower": lower, "upper": upper, "level": .95,
        "declared_family_count": len(values), "task_count": len(histories),
        "history_count": len({a["history"] for a, _ in pairs}),
        "per_family_delta": means, "bootstrap_samples": samples, "bootstrap_seed": seed,
        "degenerate_interval": bool(values) and lower == upper,
        "weighting": "equal family; equal task within family; equal history then repeat within task",
        "method": "descriptive percentile family-cluster bootstrap conditional on frozen histories",
        "unknown_handling": "zero successes in all-attempt delta, not a confirmed semantic failure",
        "semantic_family_independence_certified": False, "inferential_claim_authorized": False,
    }


def _pair(pairs, *, seed, samples, delta, min_families, min_histories):
    counts = Counter()
    for candidate, baseline in pairs:
        a, b = candidate["status"], baseline["status"]
        category = "unknown" if "unknown" in (a, b) else (
            "tie" if a == b else "win" if a == "pass" else "loss")
        counts[category] += 1
    base_correct = [(a, b) for a, b in pairs if b["status"] == "pass"]
    regressions = sum(a["status"] == "fail" for a, _ in base_correct)
    unknown_on_correct = sum(a["status"] == "unknown" for a, _ in base_correct)
    missing_candidate = sum(a["missing"] for a, _ in pairs)
    missing_baseline = sum(b["missing"] for _, b in pairs)
    ci = _cluster_delta(pairs, seed=seed, samples=samples)
    reasons = []
    if ci["declared_family_count"] < min_families:
        reasons.append("insufficient_declared_families")
    if ci["history_count"] < min_histories:
        reasons.append("insufficient_learning_histories")
    if counts["unknown"]:
        reasons.append("unknown_pairs")
    if missing_candidate or missing_baseline:
        reasons.append("missing_positions")
    if ci["degenerate_interval"]:
        reasons.append("degenerate_bootstrap_does_not_establish_noninferiority")
    observation = (ci["lower"] > -delta if not reasons and ci["lower"] is not None else None)
    return {
        "positions": len(pairs), **{key: counts[key] for key in ("win", "loss", "tie", "unknown")},
        "known_pair_coverage": _ratio(len(pairs) - counts["unknown"], len(pairs)),
        "missing_candidate_positions": missing_candidate, "missing_baseline_positions": missing_baseline,
        "baseline_correct_to_fail": _ratio(regressions, len(base_correct)),
        "baseline_correct_to_unknown": _ratio(unknown_on_correct, len(base_correct)),
        "regression_task_count": len({a["task_id"] for a, _ in base_correct if a["status"] == "fail"}),
        "regression_family_count": len({a["family_id"] for a, _ in base_correct if a["status"] == "fail"}),
        "all_attempt_delta": (sum(int(a["status"] == "pass") - int(b["status"] == "pass")
                                  for a, b in pairs) / len(pairs) if pairs else None),
        "family_equal_delta_ci": ci,
        "noninferiority_diagnostic": {
            "status": "pending", "margin": delta, "min_families": min_families,
            "min_histories": min_histories, "insufficient_evidence": reasons,
            "descriptive_lower_exceeds_negative_margin": observation,
            "reason": "descriptive interval only; no preregistered formal noninferiority test or authorization",
            "safety_guarantee": False,
        },
    }


def summarize(rows, expected_positions, *, bootstrap_seed=20260925, bootstrap_samples=2000,
              noninferiority_delta=.02, min_families=20, min_histories=3,
              candidate_conditions=("local", "mechanism")):
    """Measure a fixed, explicit grid; missing observations remain unknown.

    Manifest/rows require ``history`` (str), task/family/domain/region, nonnegative
    repeat, condition and exposure. Observations also require status and boolean
    skill_applied. Both exposures must explicitly register their own baselines;
    no receipt is silently copied. Optional request/receipt/trajectory SHA256s
    describe reuse, not independence. Extra payloads are ignored, not forwarded.

    ``candidate_conditions`` names the ordered pair of candidate arms. They
    must be distinct bounded identifiers, never No-Skill/Current. Both are
    compared with the unchanged baselines; the second is additionally compared
    with the first. Names are validated per invocation, not globally renamed
    in input records or output JSON. Omitting it retains local/mechanism names.

    NI is always Pending: an ordinary descriptive bootstrap is not a calibrated
    noninferiority gate. The configured margin and sample minima only annotate
    its descriptive evidence. No model, network, code execution, or writes occur.
    """
    require(type(bootstrap_seed) is int and bootstrap_seed >= 0, "Nonnegative bootstrap seed required")
    require(type(bootstrap_samples) is int and 1 <= bootstrap_samples <= 100000,
            "Bounded positive bootstrap sample count required")
    require(type(noninferiority_delta) in (int, float) and math.isfinite(noninferiority_delta)
            and 0 <= noninferiority_delta <= 1, "Finite noninferiority margin in [0,1] required")
    require(type(min_families) is int and min_families >= 1, "Positive family minimum required")
    require(type(min_histories) is int and min_histories >= 1, "Positive history minimum required")
    require(type(candidate_conditions) in (tuple, list) and len(candidate_conditions) == 2,
            "Exactly two ordered candidate condition names required")
    candidates = tuple(candidate_conditions)
    require(all(type(name) is str and re.fullmatch(r"[A-Za-z][A-Za-z0-9_.-]{0,63}", name)
                for name in candidates), "Candidate conditions must be bounded identifiers")
    require(len(set(candidates)) == 2 and not set(candidates) & {"no_skill", "current"},
            "Candidate conditions must be distinct and cannot alias No-Skill or Current")
    grid = _grid(rows, expected_positions, conditions=("no_skill", "current", *candidates))
    grouped, indexed = defaultdict(list), {}
    for row in grid:
        grouped[(row["exposure"], row["condition"])].append(row)
        indexed[_key(row)] = row
    arms = {}
    for (exposure, condition), group in sorted(grouped.items()):
        entry = _arm(group)
        for field in ("region", "domain", "history"):
            entry["by_" + field] = {
                value: _arm([row for row in group if row[field] == value])
                for value in sorted({row[field] for row in group})}
        domain_rates = [part["all_attempt_success"]["value"] for part in entry["by_domain"].values()]
        entry["worst_domain_all_attempt_success"] = min(domain_rates) if domain_rates else None
        arms[f"{exposure}/{condition}"] = entry
    comparisons = {}
    config = {"seed": bootstrap_seed, "samples": bootstrap_samples, "delta": noninferiority_delta,
              "min_families": min_families, "min_histories": min_histories}
    for (exposure, condition), group in sorted(grouped.items()):
        baselines = ("no_skill",) if condition == "current" else (
            ("no_skill", "current", candidates[0]) if condition == candidates[1] else ("no_skill", "current"))
        if condition == "no_skill":
            continue
        for baseline in baselines:
            if (exposure, baseline) not in grouped:
                continue
            pairs = [(row, indexed[(row["history"], row["task_id"], row["repeat"], baseline, exposure)])
                     for row in group]
            entry = _pair(pairs, **config)
            for field in ("region", "domain", "history"):
                entry["by_" + field] = {
                    value: _pair([(a, b) for a, b in pairs if a[field] == value], **config)
                    for value in sorted({a[field] for a, _ in pairs})}
            entry["worst_domain_all_attempt_delta"] = min(
                part["all_attempt_delta"] for part in entry["by_domain"].values())
            entry["candidate_condition"], entry["baseline_condition"], entry["exposure"] = condition, baseline, exposure
            comparisons[f"{exposure}/{condition}_vs_{baseline}"] = entry
    references = {}
    for field in ("request_hash", "receipt_hash", "trajectory_hash"):
        values = [row[field] for row in grid if field in row]
        references[field] = {"referenced_positions": len(values), "unique_references": len(set(values)),
                             "aliased_positions": len(values) - len(set(values))}
    return seal({
        "version": VERSION, "purpose": "host_descriptive_mechanism_pilot_not_a_gate",
        "expected_positions": len(grid), "observed_positions": sum(not row["missing"] for row in grid),
        "missing_positions": sum(row["missing"] for row in grid), "records_hash": digest(grid),
        "missing_keys": [{field: row[field] for field in KEY} for row in grid if row["missing"]],
        "arms": arms, "comparisons": comparisons, "reference_reuse": references,
        "bootstrap_seed": bootstrap_seed, "bootstrap_samples": bootstrap_samples,
        "diagnostic_configuration": {"noninferiority_delta": noninferiority_delta,
                                     "min_families": min_families, "min_histories": min_histories},
        "deployment_authorized": False, "skill_admission_authorized": False,
        "cross_domain_authorized": False, "formal_noninferiority_established": False,
        "limitations": [
            "Caller-supplied identities/statuses are not authenticated here; hashes only bind normalized records.",
            "Declared family labels need external validation; repeats and cache aliases add no independent families.",
            "Family bootstrap conditions on observed histories, is unadjusted for multiple comparisons, and is descriptive.",
            "All-attempt success includes unknown in its denominator, separately from confirmed failure.",
            "A conditional no-injection position may be a scope fallback or an empty Skill; it is not learning success.",
            "Missing references do not imply independent requests; output costs must be reconciled with the caller ledger.",
        ],
    })
