"""Read-only S0/S1 Coding comparison; no inference, rescoring or panel loading.

Uses sealed metadata and byte hashes, never inspects task answers or model text.
Development results are descriptive, not independent final/generalization claims.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import random
from collections import Counter
from contextlib import ExitStack

from skillopt.coevolution_v5.core import seal
from skillopt.continual_eval.core import load_checkpoint, read_json, require, safe_path, write_json
from skillopt.continual_eval.runner import _costs, _stored_calls, _valid_prediction
from skillopt.validator_pilot.api import digest

VERSION = "cross-run-coding-paired-report-v2"
BOOTSTRAP_SEED = 20261001
BOOTSTRAP_RESAMPLES = 10_000
GROUPS = ("train", "selection", "not_used_by_this_learning")
NATURAL_COUNTS = dict(zip(GROUPS, (65, 64, 271)))
SAFE_REASONS = {"model_response_truncated", "model_call_unavailable", "empty_or_oversized_model_response",
                "native_timeout", "native_execution_unavailable", "container_cleanup_unconfirmed",
                "invalid_native_receipt", "operator_closed_interrupted_attempt"}


def _sha(path):
    return hashlib.sha256(safe_path(path).read_bytes()).hexdigest()


def _source(root, hashes):
    require(type(hashes) is dict and hashes, "Missing frozen source identity")
    for name, expected in hashes.items():
        path = safe_path(root / "skillopt" / name)
        require(path.is_relative_to(root / "skillopt") and _sha(path) == expected, "Frozen source changed")


def _plan(root, source):
    # load_plan()/runner.report() would load hidden task fields or write reports.
    value = read_json(root / "plan.json", sealed=True)
    require(value["config"]["partition"] == "development"
            and all(t["partition"] == "development" for t in value["tasks"]), "Only development comparisons allowed")
    require(value["order"][0] == "bigcodebench" and value["version"] == "continual-eval-v2",
            "Expected Coding-first v2 evaluation")
    require(all(value[k] == value["config"][k] for k in ("version", "order", "repeats")), "Plan/configuration mismatch")
    _source(source, value["source_identity"])
    require(type(value["repeats"]) is int and value["repeats"] > 0, "Invalid repeat roster")
    return value


def _comparable(left, right):
    require(left["source_identity"] == right["source_identity"], "Evaluation source identities differ")
    require(left["host_runtime"] == right["host_runtime"], "Host runtime identities differ")
    require(left["tasks"] == right["tasks"] and left["repeats"] == right["repeats"], "Task/repeat roster differs")
    require(left["evidence_kind"] == right["evidence_kind"], "Evidence kinds differ")
    for value in (left, right):
        require(value["panels"]["bigcodebench"]["status"] == "present", "Coding panel unavailable")
    panels = lambda p: {b: {k: v for k, v in row.items() if k != "path"} for b, row in p["panels"].items()}  # noqa: E731
    require(panels(left) == panels(right), "Frozen panel identity differs")
    config = lambda p: {k: v for k, v in p["config"].items() if k not in {"methods", "panels"}}  # noqa: E731
    require(config(left) == config(right) and left["exposure_hash"] == right["exposure_hash"],
            "Solver/configuration differs beyond method and copied panel paths")


def _learning(manifest_path, result_path, checkpoint, plan):
    value = read_json(manifest_path, sealed=True)
    result = read_json(result_path, sealed=True)
    root = result_path.parent
    require(value["method"] == checkpoint["method"] and value["model"] == plan["config"]["model"]
            and value["runtime"] == plan["config"]["runtime"].get("bigcodebench", {}),
            "Learning method/model/native configuration differs")
    require(value["parent_skill"] == "" and result["status"] == "completed", "No completed empty-parent learning result")
    if "protocol_hash" in result:
        protocol = read_json(root / "protocol.json", sealed=True)
        require(protocol["record_hash"] == result["protocol_hash"] and protocol["manifest"] == value,
                "Branch result/manifest binding differs")
        skill = result.get("selected_skill")
    else:
        identity = read_json(root / "identity.json", sealed=True)
        require(identity["record_hash"] == result["identity_hash"] and identity["manifest"] == value,
                "Learning result/manifest binding differs")
        skill = result.get("candidate_skill")
    require(type(skill) is str and skill.strip() and skill == checkpoint["skill_text"],
            "S1 must be a nonempty Skill from the completed learning result")
    for name, expected in result["artifacts"].items():
        path = safe_path(root / name)
        require(path.is_relative_to(root) and _sha(path) == expected, "Learning artifact changed")
    require(set(value["authorized_tasks"].values()) <= {"train", "selection"}, "Unsupported learning role")
    return value, result


def _position(root, plan, checkpoint, task, repeat, service):
    request = {"plan_hash": plan["record_hash"], "checkpoint_hash": checkpoint["record_hash"],
               "benchmark": "bigcodebench", "task_hash": task["task_hash"], "repeat": repeat}
    base = root / "predictions" / digest(request)
    receipts = _stored_calls(base)
    for path in (base / "calls").glob("*.json"):
        call = read_json(path, sealed=True)
        require(call["request"]["position"] == request
                and call["receipt"]["request"]["service"] == service
                and call["receipt"]["request"]["model"] == plan["config"]["model"]["name"]
                and call["request"]["max_tokens"] == plan["config"]["model"]["max_tokens"]
                and call["receipt"]["request"]["max_tokens"] == plan["config"]["model"]["max_tokens"],
                "Call position/model/service binding or token budget differs")
        if call["receipt"].get("ok") and plan["config"]["model"]["provider"] != "fixture":
            require(call["receipt"].get("returned_model") == plan["config"]["model"]["name"], "Returned model differs")
    intents = len(list((base / "call_intents").glob("*.json")))
    require(intents >= len(receipts), "More calls than intents")
    costs = _costs(receipts, unclosed=intents - len(receipts))
    prediction = None
    if (base / "prediction.json").exists():
        prediction = read_json(base / "prediction.json", sealed=True)
        require(prediction["request"] == request and prediction["costs"] == costs, "Prediction/cost binding differs")
        require(read_json(base / "intent.json", sealed=True) == seal(request), "Prediction intent differs")
        _valid_prediction(prediction["prediction"])
    target = root / "host_only/scores" / (base.name + ".json")
    if not target.exists():
        return {"status": "missing", "prediction_present": prediction is not None}, receipts, intents - len(receipts)
    row = read_json(target, sealed=True)
    require(prediction is not None and row["prediction_hash"] == prediction["record_hash"], "Score/prediction binding differs")
    require(row["plan_hash"] == plan["record_hash"] and row["checkpoint_hash"] == checkpoint["record_hash"]
            and all(row[k] == checkpoint[k] for k in ("method", "history", "stage"))
            and all(row[k] == task[k] for k in ("benchmark", "task_id", "family_id"))
            and row["repeat"] == repeat and row["costs"] == costs, "Score task/repeat/cost binding differs")
    intent = read_json(root / "host_only/score_intents" / target.name, sealed=True)
    require(intent == seal({"request": request, "prediction_hash": prediction["record_hash"]}), "Score intent differs")
    require(row["status"] in {"pass", "fail", "unknown"}, "Invalid score status")
    if row["status"] == "unknown":
        require(row["score"] is None, "Unknown cannot be a numerical score")
    else:
        require(row["score"] == int(row["status"] == "pass")
                and prediction["prediction"]["status"] == "available", "Invalid Coding score")
        if plan["config"]["model"]["provider"] != "fixture":
            require(row.get("runtime_image_id") == plan["config"]["runtime"]["bigcodebench"]["image"]
                    and row.get("cleanup_confirmed") is True, "Native execution identity/cleanup unverified")
    reason = row.get("reason", "")
    require(type(reason) is str, "Invalid reason metadata")
    safe_reason = reason if reason in SAFE_REASONS else "other:" + digest(reason)
    return {"status": row["status"], "score": row["score"], "reason_code": safe_reason,
            "score_hash": row["record_hash"], "prediction_hash": prediction["record_hash"]}, receipts, intents - len(receipts)


def _paired_uncertainty(rows):
    """Conditional, position-weighted paired delta; resample whole families.

    Repeat positions travel together with their frozen lexical family. Unknown
    and missing outcomes never enter the bootstrap as zeros. The separate full
    roster bounds enumerate possible [0,1] completions, not an imputed score.
    """
    families = {}
    unresolved = Counter()
    lower_sum = upper_sum = 0.0
    for row in rows:
        if row["comparison"] in {"unknown", "missing"}:
            unresolved[row["comparison"]] += 1
        else:
            delta = row["candidate"]["score"] - row["baseline"]["score"]
            family = families.setdefault(row["family_hash"], [0.0, 0])
            family[0] += delta
            family[1] += 1

        def bounds(side):
            return ((side["score"], side["score"]) if side["status"] in {"pass", "fail"}
                    else (0.0, 1.0))

        left, right = bounds(row["baseline"]), bounds(row["candidate"])
        lower_sum += right[0] - left[1]
        upper_sum += right[1] - left[0]
    clusters = [families[key] for key in sorted(families)]
    denominator = sum(count for _, count in clusters)
    mean = sum(total for total, _ in clusters) / denominator if denominator else None
    interval = None
    if len(clusters) >= 2:
        rng = random.Random(BOOTSTRAP_SEED)
        draws = []
        for _ in range(BOOTSTRAP_RESAMPLES):
            sampled = [clusters[rng.randrange(len(clusters))] for _ in clusters]
            draws.append(sum(total for total, _ in sampled) / sum(count for _, count in sampled))
        draws.sort()

        def percentile(probability):
            index = (len(draws) - 1) * probability
            low = int(index)
            return draws[low] + (draws[min(low + 1, len(draws) - 1)] - draws[low]) * (index - low)

        interval = {"lower": percentile(0.025), "upper": percentile(0.975)}
    return {"status": "descriptive_available" if interval is not None else "pending",
            "reason": "conditional_on_known_pairs" if interval is not None else "fewer_than_two_known_clusters",
            "mean_paired_delta_known": mean, "known_pair_denominator": denominator,
            "known_cluster_count": len(clusters),
            "excluded_unknown_pairs": unresolved["unknown"], "excluded_missing_pairs": unresolved["missing"],
            "cluster_unit": "frozen_lexical_family_hash_not_proven_semantically_independent",
            "estimand": "candidate_minus_baseline_mean_over_known_positions",
            "bootstrap": {"seed": BOOTSTRAP_SEED, "resamples": BOOTSTRAP_RESAMPLES,
                          "resamples_executed": BOOTSTRAP_RESAMPLES if interval is not None else 0,
                          "confidence_level": 0.95, "method": "whole_family_percentile_linear_interpolation",
                          "rng": "python_random_Random_randrange", "interval": interval,
                          "zero_width_sampling_degeneracy": interval is not None and interval["lower"] == interval["upper"],
                          "degeneracy_note": "A zero-width empirical bootstrap interval does not establish certainty, absence of risk or generalization."},
            "full_roster_completion_bounds": {
                "positions": len(rows), "unresolved_pairs": sum(unresolved.values()),
                "lower": lower_sum / len(rows) if rows else None,
                "upper": upper_sum / len(rows) if rows else None,
                "semantics": "Mathematical bounds if every unresolved outcome lies in [0,1]; not a confidence interval or imputation."},
            "deployment_evidence": False}


def _summary(rows):
    counts = Counter(r["comparison"] for r in rows)
    return {"positions": len(rows), "tasks": len({r["task_hash"] for r in rows}),
            "families": len({r["family_hash"] for r in rows}),
            "pair_counts": {k: counts[k] for k in ("win", "loss", "tie", "unknown", "missing")},
            "baseline_counts": dict(Counter(r["baseline"]["status"] for r in rows)),
            "candidate_counts": dict(Counter(r["candidate"]["status"] for r in rows)),
            "paired_known_denominator": counts["win"] + counts["loss"] + counts["tie"],
            "net_wins": counts["win"] - counts["loss"],
            "uncertainty": _paired_uncertainty(rows)}


def _compare(baseline_root, candidate_root, *, baseline_source, candidate_source, learning_manifest,
            learning_result, method, history="h0", fixture_group_counts=None):
    roots = [safe_path(p) for p in (baseline_root, candidate_root)]
    left, right = [_plan(root, safe_path(source)) for root, source in zip(roots, (baseline_source, candidate_source))]
    _comparable(left, right)
    checkpoints = [load_checkpoint(roots[0], "no_skill", history, 0, left),
                   load_checkpoint(roots[1], method, history, 1, right)]
    require(checkpoints[0]["skill_text"] == "" and checkpoints[1]["skill_text"].strip(), "Require empty S0/nonempty S1")
    learned, learned_result = _learning(safe_path(learning_manifest), safe_path(learning_result), checkpoints[1], right)
    natural = left["config"]["model"]["provider"] != "fixture"
    require(not natural or fixture_group_counts is None, "Natural task-count requirements cannot be overridden")
    expected_counts = NATURAL_COUNTS if fixture_group_counts is None else fixture_group_counts
    tasks = [t for t in left["tasks"] if t["benchmark"] == "bigcodebench"]
    require(len({t["task_hash"] for t in tasks}) == len(tasks), "Duplicate task hash")
    require(len({t["task_id"] for t in tasks}) == len(tasks), "Duplicate task identity")
    by_hash = {t["task_hash"]: t for t in tasks}
    require(set(learned["authorized_tasks"]) <= set(by_hash), "Learning tasks outside evaluation roster")
    groups = {name: [] for name in GROUPS}
    for task in tasks:
        group = learned["authorized_tasks"].get(task["task_hash"], GROUPS[2])
        groups[group].append(task)
    require({k: len(v) for k, v in groups.items()} == expected_counts, "Unexpected training/selection/unseen task counts")
    families = {k: {t["family_id"] for t in v} for k, v in groups.items()}
    require(families["train"] == set(learned["train_families"])
            and families["selection"] == set(learned["selection_families"])
            and not families["train"] & families["selection"], "Learning family identity or disjointness differs")
    if natural:
        require(len(families["train"]) == len(families["selection"]) == 64, "Unexpected independent learning families")
    service_hashes, services = [], []
    for root in roots:
        service = read_json(root / "model_service.json", sealed=True)
        service_hashes.append(service.pop("record_hash"))
        services.append(service)
    require(service_hashes[0] == service_hashes[1], "Actual model service differs")
    pairs, receipts, unclosed = [], [[], []], [0, 0]
    for group, roster in groups.items():
        for task in roster:
            for repeat in range(left["repeats"]):
                pair = {"task_hash": task["task_hash"], "family_hash": digest(task["family_id"]),
                        "group": group, "repeat": repeat}
                for i, name in enumerate(("baseline", "candidate")):
                    item, calls, open_calls = _position(roots[i], (left, right)[i], checkpoints[i], task, repeat, services[i])
                    pair[name] = item
                    receipts[i].extend(calls)
                    unclosed[i] += open_calls
                statuses = {pair[name]["status"] for name in ("baseline", "candidate")}
                pair["comparison"] = "missing" if "missing" in statuses else "unknown" if "unknown" in statuses \
                    else "win" if pair["candidate"]["score"] > pair["baseline"]["score"] \
                    else "loss" if pair["candidate"]["score"] < pair["baseline"]["score"] else "tie"
                pairs.append(pair)
    missing = any(row["comparison"] == "missing" for row in pairs)
    return seal({"version": VERSION, "status": "pending" if missing else "completed",
        "evidence_kind": left["evidence_kind"], "partition": "development", "benchmark": "bigcodebench",
        "baseline_plan_hash": left["record_hash"], "candidate_plan_hash": right["record_hash"],
        "baseline_checkpoint_hash": checkpoints[0]["record_hash"], "candidate_checkpoint_hash": checkpoints[1]["record_hash"],
        "learning_manifest_hash": learned["record_hash"], "learning_result_hash": learned_result["record_hash"],
        "source_identity_hash": digest(left["source_identity"]), "service_hash": service_hashes[0],
        "overall": _summary(pairs), "groups": {k: _summary([r for r in pairs if r["group"] == k]) for k in GROUPS},
        "family_overlap_counts": {a + "__" + b: len(families[a] & families[b])
                                  for i, a in enumerate(GROUPS) for b in GROUPS[i + 1:]},
        "costs": {name: _costs(receipts[i], unclosed=unclosed[i]) for i, name in enumerate(("baseline", "candidate"))},
        "cost_scope": "Selected Coding S0/S1 positions including unscored/unclosed calls, not other checkpoints or whole-run spend.",
        "learning_costs": {name: {k: v for k, v in learned_result.get(name, {}).items()
            if k in {"logical_calls", "terminal_calls", "unclosed_calls", "http_attempts", "reported_tokens_known_subtotal",
                     "usage_complete", "retry_inclusive_usage_known", "missing_usage_calls"}}
            for name in ("costs", "new_costs", "inherited_costs") if name in learned_result},
        "pairs": pairs, "native_scores_reexecuted": False, "new_model_calls": 0, "old_records_modified": False,
        "deployment_authorized": False, "independent_final_evidence": False,
        "limitations": ["Not-used tasks may have historical exposure; they are not final or fully unseen.",
                        "Repeated positions are not additional independent tasks or families.",
                        "Known-pair wins/losses exclude but retain explicit unknown and missing positions.",
                        "Family clusters are lexical metadata, not established semantic independence.",
                        "Exploratory bootstrap intervals condition on known pairs; they do not correct missingness, selection, historical exposure or multiple comparisons.",
                        "Zero-width bootstrap intervals, including all observed ties or wins, reflect empirical resampling degeneracy, not certainty, no risk or universal transfer.",
                        "Full-roster completion bounds are not semantic scores, confidence intervals or deployment gates.",
                        "Sealed receipt/source consistency is not an independent native grader rerun."]})


def compare(baseline_root, candidate_root, **kwargs):
    # Only shared, existing locks; never create an experiment lock or race a
    # writer while reading score/prediction pairs and costs.
    protected = {safe_path(baseline_root), safe_path(candidate_root), safe_path(kwargs["learning_result"]).parent}
    with ExitStack() as stack:
        for root in sorted(protected):
            handle = stack.enter_context(safe_path(root / ".writer.lock").open("rb"))
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_SH | fcntl.LOCK_NB)
            except BlockingIOError:
                raise ValueError("Evidence is still being written; retry read-only report later") from None
        return _compare(baseline_root, candidate_root, **kwargs)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("baseline-root", "candidate-root", "baseline-source", "candidate-source", "learning-manifest", "learning-result", "method", "output"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--history", default="h0")
    args = vars(parser.parse_args(argv))
    output = safe_path(args.pop("output"))
    protected = [safe_path(args[k]) for k in ("baseline_root", "candidate_root", "baseline_source", "candidate_source")]
    protected += [safe_path(args["learning_result"]).parent, safe_path(args["learning_manifest"]).parent]
    require(not any(output == p or output.is_relative_to(p) for p in protected), "Report output must be outside source/evidence directories")
    result = compare(**args)
    write_json(output, result)
    print(json.dumps({k: result[k] for k in ("status", "record_hash", "overall", "groups", "new_model_calls")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
