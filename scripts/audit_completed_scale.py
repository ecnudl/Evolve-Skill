"""Read-only, post-completion diagnostic; never reads artifacts before the barrier.

No network, model, candidate execution, or credentials. Default output is stdout;
an optional immutable archive must be outside the original run directory. This
is a post-hoc supplement, not part of the frozen study's primary analysis.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import tempfile
from collections import defaultdict
from itertools import combinations
from pathlib import Path

SINGLE_SHOT_SEED = 20260910
SINGLE_SHOT_DRAWS = 2000
SINGLE_SHOT_SIZES = (5, 10, 20, 32)


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(",", ":")).encode("utf-8")).hexdigest()


def _observable(row):
    return row["target_ok"] and row["execution_ok"] and type(row["hard"]) is bool


def _distinct(rows):
    return {"response_draws": len(rows), "distinct_tasks": len({r["id"] for r in rows}),
            "distinct_families": len({r["family"] for r in rows}),
            "task_ids": sorted({r["id"] for r in rows}),
            "family_ids": sorted({r["family"] for r in rows})}


def solver_details(rows):
    """Cross-tab exact source-text identity with observed same-task hard flips."""
    output = {}
    for split in ("dev", "holdout", "all"):
        selected = [r for r in rows if split == "all" or r["split"] == split]
        by_arm = {}
        for arm in ("noskill", "generic_control", "mechanism_skill"):
            values = [r for r in selected if r["arm"] == arm]
            observed = [r for r in values if _observable(r)]
            groups = defaultdict(list)
            for row in values:
                groups[row["id"]].append(row)
            details = []
            totals = {name: 0 for name in ("observed_repeat_pairs", "hard_flip_pairs",
                      "code_comparable_pairs", "identical_code_pairs", "different_code_pairs",
                      "identical_code_hard_flip_pairs", "different_code_hard_flip_pairs",
                      "unavailable_code_hard_flip_pairs", "response_comparable_pairs", "identical_response_pairs")}
            for identity, group in sorted(groups.items()):
                group.sort(key=lambda row: row["repeat"])
                available = [r for r in group if _observable(r)]
                codes = [r["code"] for r in available if isinstance(r.get("code"), str)]
                hard_flip = len({r["hard"] for r in available}) > 1
                inconsistent = []
                for left, right in combinations(available, 2):
                    totals["observed_repeat_pairs"] += 1
                    flip = left["hard"] != right["hard"]
                    totals["hard_flip_pairs"] += flip
                    if isinstance(left.get("response"), str) and isinstance(right.get("response"), str):
                        totals["response_comparable_pairs"] += 1
                        totals["identical_response_pairs"] += left["response"] == right["response"]
                    if isinstance(left.get("code"), str) and isinstance(right.get("code"), str):
                        same = left["code"] == right["code"]
                        totals["code_comparable_pairs"] += 1
                        totals["identical_code_pairs" if same else "different_code_pairs"] += 1
                        totals["identical_code_hard_flip_pairs" if same else "different_code_hard_flip_pairs"] += flip
                        if same and flip:
                            inconsistent.append([left["repeat"], right["repeat"]])
                    elif flip:
                        totals["unavailable_code_hard_flip_pairs"] += 1
                details.append({"id": identity, "family": group[0]["family"],
                                "observed_repeats": len(available), "available_code_repeats": len(codes),
                                "unique_exact_code_count": len(set(codes)),
                                "hard_flip": hard_flip, "identical_code_conflicting_hard_repeats": inconsistent,
                                "all_available_code_identical": len(codes) >= 2 and len(set(codes)) == 1,
                                "all_four_hard_pass": len(available) == 4 and all(r["hard"] for r in available),
                                "all_four_hard_fail": len(available) == 4 and not any(r["hard"] for r in available)})
            failures = [r for r in observed if not r["hard"]]
            unavailable = [r for r in values if not _observable(r)]
            complete_groups = bool(groups) and all(len(group) == 4 and {r["repeat"] for r in group} == {0, 1, 2, 3}
                                                  for group in groups.values())
            by_arm[arm] = {"rows": len(values), "observed": len(observed),
                           "hard_failures": _distinct(failures), "unavailable": _distinct(unavailable),
                           "zero_observed_failures": bool(observed) and not failures,
                           "all_expected_observed_and_pass": complete_groups and not unavailable and not failures,
                           "tasks_with_hard_flips": sum(row["hard_flip"] for row in details),
                           "tasks_with_four_successes": sum(row["all_four_hard_pass"] for row in details),
                           "tasks_with_four_failures": sum(row["all_four_hard_fail"] for row in details),
                           "task_repeat_pairs": totals, "tasks": details,
                           "not_independent_repeat_pairs": True,
                           "exact_text_only": "Different source strings do not necessarily imply different behavior."}
        output[split] = by_arm
    return output


def _effective_decision(row, guarded):
    if not _observable(row):
        return "unavailable"
    judgment = row["guarded_judgment"] if guarded else row["judgment"]
    available = row["judge_ok"] or (guarded and row["guard_forced"])
    if not available or judgment.get("schema_valid") is not True:
        return "unknown"
    decision = judgment.get("decision")
    return decision if decision in {"pass", "fail"} else "unknown"


def _artifact_key(row):
    return row["id"], row["skill_version"], row["origin"], row["target_repeat"]


def judge_details(by_arm):
    """Do not multiply the number of erroneous artifacts by judge repetitions."""
    output = {}
    for arm, rows in sorted(by_arm.items()):
        arm_output = {}
        for guarded in (False, True):
            by_origin = {}
            for origin in ("natural", "controlled"):
                selected = [r for r in rows if r["origin"] == origin]
                groups = defaultdict(list)
                for row in selected:
                    groups[_artifact_key(row)].append(row)
                categories = {}
                for category in ("false_pass", "false_reject", "unknown", "unavailable"):
                    matches = []
                    for row in selected:
                        decision = _effective_decision(row, guarded)
                        label = ("false_pass" if decision == "pass" and row["hard"] is False else
                                 "false_reject" if decision == "fail" and row["hard"] is True else decision)
                        if label == category:
                            matches.append(row)
                    categories[category] = {**_distinct(matches),
                                             "distinct_artifacts": len({_artifact_key(r) for r in matches})}
                by_origin[origin] = {"judge_draws": len(selected), "distinct_artifacts": len(groups),
                                     "distinct_tasks": len({r["id"] for r in selected}),
                                     "distinct_families": len({r["family"] for r in selected}),
                                     "hard_fail_artifacts": len({_artifact_key(r) for r in selected
                                                                  if _observable(r) and r["hard"] is False}),
                                     "hard_pass_artifacts": len({_artifact_key(r) for r in selected
                                                                  if _observable(r) and r["hard"] is True}),
                                     "error_counts": categories,
                                     "artifacts_with_decision_variation": sum(
                                         len({_effective_decision(r, guarded) for r in group}) > 1
                                         for group in groups.values()),
                                     "artifacts_with_strict_pass_fail_flips": sum(
                                         {_effective_decision(r, guarded) for r in group} == {"pass", "fail"}
                                         for group in groups.values())}
            arm_output["guarded" if guarded else "raw"] = by_origin
        output[arm] = arm_output
    return output


def display_tables(analysis, details):
    output = {}
    for split, report in analysis["splits"].items():
        entries = {}
        for name, contrast in report["contrasts"].items():
            bootstrap = contrast["family_cluster_bootstrap"]
            both_ceiling = all(details[split][contrast[key]]["all_expected_observed_and_pass"]
                               for key in ("candidate", "reference"))
            entries[name] = {"macro_family_delta": contrast["primary_macro_family_delta"],
                             "micro_task_delta": contrast["micro_task_delta"],
                             "family_deltas": contrast["family_deltas"],
                             "per_global_replicate": contrast["per_global_replicate"],
                             "missing_pairs": contrast["n_missing_pairs"],
                             "task_wins_losses_ties": contrast["task_discordance"],
                             "ci95": bootstrap["ci95"], "ci90": bootstrap["ci90"],
                             "few_clusters": bootstrap["few_cluster_warning"],
                             "degenerate_bootstrap": bootstrap.get("bootstrap_distribution_degenerate"),
                             "both_arms_observed_ceiling": both_ceiling,
                             "equivalence_established": False,
                             "diagnostic_warning": "Ceiling-limited; degenerate intervals are not equivalence or precision evidence."
                             if both_ceiling else "Exploratory family resampling; selected author-created families are not a random population sample.",
                             "batch_size_sign_diagnostics": contrast["task_batch_subsampling"]}
        output[split] = entries
    return output


def _sample_stats(values):
    ordered = sorted(values)

    def percentile(percent):
        if not ordered:
            return None
        index = (len(ordered) - 1) * percent / 100
        lower = int(index)
        upper = min(lower + 1, len(ordered) - 1)
        return ordered[lower] + (ordered[upper] - ordered[lower]) * (index - lower)

    return {"n_evaluable_draws": len(ordered),
            "positive_fraction": sum(v > 1e-12 for v in ordered) / len(ordered) if ordered else None,
            "zero_fraction": sum(abs(v) <= 1e-12 for v in ordered) / len(ordered) if ordered else None,
            "negative_fraction": sum(v < -1e-12 for v in ordered) / len(ordered) if ordered else None,
            "percentiles": {str(q): percentile(q) for q in (2.5, 5, 50, 95, 97.5)}}


def single_shot_batch_sensitivity(rows, *, draws=SINGLE_SHOT_DRAWS, seed=SINGLE_SHOT_SEED,
                                  sizes=SINGLE_SHOT_SIZES):
    """Conditional resampling of an observed global wave and paired task subset.

    One repeat label is shared by all tasks in a draw. Task sampling never
    replaces missing values with zero, and never selects a different arm repeat.
    The same selections are used for both contrasts; all tasks remain in the
    sampling pool even when a particular selected pair is unavailable.
    """
    if type(draws) is not int or draws < 1 or type(seed) is not int or seed < 0:
        raise ValueError("Diagnostic draws and seed must be valid integers")
    sizes = tuple(sizes)
    if any(type(size) is not int or size < 1 for size in sizes) or len(set(sizes)) != len(sizes):
        raise ValueError("Diagnostic sizes must be unique positive integers")
    rows = list(rows)
    indexed = {(row["id"], row["arm"], row["repeat"]): row for row in rows}
    if len(indexed) != len(rows):
        raise ValueError("Duplicate single-shot task/arm/repeat identity")
    metadata = {}
    for row in rows:
        value = row["family"], row["split"]
        if row["id"] in metadata and metadata[row["id"]] != value:
            raise ValueError("Inconsistent single-shot task metadata")
        if type(row["repeat"]) is not int or row["repeat"] not in (0, 1, 2, 3):
            raise ValueError("Diagnostic requires the frozen four repeat labels")
        metadata[row["id"]] = value
    scopes = {}
    for split in ("dev", "holdout", "all"):
        task_ids = sorted(identity for identity, (_, task_split) in metadata.items()
                          if split == "all" or task_split == split)
        comparisons = {}
        for reference in ("noskill", "generic_control"):
            entries = {}
            for size in sizes:
                draw_seed = int(_digest({"seed": seed, "split": split, "size": size})[:16], 16)
                shared = {"tasks_per_draw": size, "draws_requested": draws, "seed": draw_seed,
                          "without_replacement_within_draw": True,
                          "one_global_repeat_shared_by_all_selected_tasks": True}
                if size > len(task_ids):
                    entries[str(size)] = {**shared, "status": "insufficient_tasks", "draws_executed": 0}
                    continue
                rng = random.Random(draw_seed)
                choices = [(rng.randrange(4), sorted(rng.sample(task_ids, size))) for _ in range(draws)]
                macro, micro, missing_counts, matched_counts, family_counts = [], [], [], [], []
                wave_counts = {str(repeat): 0 for repeat in range(4)}
                missing_id_counts = defaultdict(int)
                per_wave_macro = {str(repeat): [] for repeat in range(4)}
                for repeat, chosen in choices:
                    wave_counts[str(repeat)] += 1
                    family_values = defaultdict(list)
                    task_values = []
                    for identity in chosen:
                        candidate = indexed.get((identity, "mechanism_skill", repeat))
                        base = indexed.get((identity, reference, repeat))
                        if candidate is None or base is None or not _observable(candidate) or not _observable(base):
                            missing_id_counts[identity] += 1
                            continue
                        difference = int(candidate["hard"]) - int(base["hard"])
                        family_values[metadata[identity][0]].append(difference)
                        task_values.append(difference)
                    matched_counts.append(len(task_values))
                    missing_counts.append(size - len(task_values))
                    family_counts.append(len(family_values))
                    if task_values:
                        family_mean = sum(sum(values) / len(values) for values in family_values.values()) / len(family_values)
                        macro.append(family_mean)
                        micro.append(sum(task_values) / len(task_values))
                        per_wave_macro[str(repeat)].append(family_mean)
                entries[str(size)] = {
                    **shared, "status": "post_hoc_conditional_observed_wave_diagnostic", "draws_executed": draws,
                    "sampled_repeat_task_choices_sha256": _digest(choices), "global_repeat_draw_counts": wave_counts,
                    "macro_family_delta": _sample_stats(macro), "micro_task_delta": _sample_stats(micro),
                    "by_selected_global_repeat_macro_delta": {repeat: _sample_stats(values)
                                                               for repeat, values in per_wave_macro.items()},
                    "selected_pairs_total": size * draws, "matched_pairs_total": sum(matched_counts),
                    "missing_pairs_total": sum(missing_counts),
                    "draws_with_missing_pairs": sum(value > 0 for value in missing_counts),
                    "draws_without_observable_pairs": draws - len(macro),
                    "matched_tasks_per_draw_min_max": [min(matched_counts), max(matched_counts)],
                    "observed_families_per_draw_min_max": [min(family_counts), max(family_counts)],
                    "selected_missing_pair_count_by_task": dict(sorted(missing_id_counts.items()))}
            comparisons[f"mechanism_skill_vs_{reference}"] = {"candidate": "mechanism_skill", "reference": reference,
                                                              "sizes": entries}
        scopes[split] = {"task_pool_size": len(task_ids), "task_pool_ids": task_ids, "contrasts": comparisons}
    return {"label": "POSTHOC-DIAGNOSTIC: single-shot observed-wave batch sensitivity",
            "draws_per_size": draws, "base_seed": seed, "sizes": list(sizes), "global_repeats": [0, 1, 2, 3],
            "scopes": scopes, "separate_from_frozen_four_repeat_average_subsampling": True,
            "sampling": "Uniformly select one of four observed global waves, then M task IDs without replacement; pair arms on identical task/wave.",
            "missingness": "Selected unavailable pairs are omitted, never zero-filled. Signs/quantiles condition on evaluable draws; missing counts remain explicit.",
            "family_weighting": "Average observed paired task outcomes within represented family, then average represented families equally.",
            "interpretation": "Conditional sensitivity of these four observed serving waves; not the distribution of a future experiment or probability of true benefit.",
            "not_new_evidence": True, "does_not_reweight_frozen_main_analysis": True}


def audit_completed(root: Path):
    root = Path(root)
    inputs = {}

    def read(name):
        payload = (root / name).read_bytes()
        inputs[name] = hashlib.sha256(payload).hexdigest()
        return json.loads(payload)

    # The first and only allowed read until a completed result is established.
    results = read("results.json")
    if results.get("status") != "complete":
        raise ValueError("Completion barrier not met; no target/judge artifacts read")
    protocol = read("protocol.json")
    if results.get("protocol_hash") != _digest(protocol):
        raise ValueError("Completed result and frozen protocol disagree")
    targets = read("dev_targets_frozen_private.json") + read("holdout_targets_frozen_private.json")
    expected = results["skill_analysis"]["design"]["n_expected_rows"]
    if len(targets) != expected:
        raise ValueError("Completed target matrix does not match the expected row count")
    identities = {(r["id"], r["arm"], r["repeat"]) for r in targets}
    if len(identities) != len(targets):
        raise ValueError("Duplicate target identity in completed matrix")
    design = results["skill_analysis"]["design"]
    expected_ids = {(task["id"], arm, repeat)
                    for arm, summary in results["skill_analysis"]["splits"]["all"]["arms"].items()
                    for task in summary["tasks"] for repeat in design["expected_repeats"]}
    if identities != expected_ids:
        raise ValueError("Completed target identities differ from the frozen analysis matrix")
    heldout_judges = read("holdout_judgments.json")
    dev_judges = read("dev_judgments.json")
    details = solver_details(targets)
    return {"version": "post-completion-scale-audit-v2", "post_hoc_descriptive_only": True,
            "completion_barrier_checked": True, "input_file_sha256": inputs,
            "audit_code_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "solver": details, "tables": display_tables(results["skill_analysis"], details),
            "single_shot_batch_sensitivity": single_shot_batch_sensitivity(targets),
            "judges": {"dev": judge_details(dev_judges), "holdout": judge_details(heldout_judges)},
            "limitations": ["Author-created tasks/families are not a random benchmark/domain sample.",
                            "Repeat pairs, bootstrap draws, and subsampling draws are not independent new evidence.",
                            "Four held-out families cannot justify established equivalence or population-generalization claims.",
                            "Exact code equality is lexical; different code can implement identical behavior.",
                            "No new calls, repairs, rescoring, or model/validator promotion are performed."]}


def archive_audit(result, output: Path, run_root: Path):
    """Atomically create an external immutable archive; never replace a file."""
    requested = Path(os.path.abspath(output))
    run_requested = Path(os.path.abspath(run_root))
    destination, run_resolved = requested.resolve(), run_requested.resolve()
    if (requested == run_requested or run_requested in requested.parents
            or destination == run_resolved or run_resolved in destination.parents):
        raise ValueError("Audit archive must be strictly outside the original run directory")
    payload = (json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n").encode("utf-8")
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".scale-audit-", dir=destination.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, destination)
        except FileExistsError:
            if destination.read_bytes() != payload:
                raise ValueError("Immutable audit archive already exists with different contents") from None
    finally:
        Path(temporary).unlink(missing_ok=True)
    return {"path": str(destination), "sha256": hashlib.sha256(payload).hexdigest(), "immutable": True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True, type=Path)
    parser.add_argument("--output", type=Path, help="Optional immutable JSON archive strictly outside --run")
    args = parser.parse_args()
    try:
        result = audit_completed(args.run)
        archive = archive_audit(result, args.output, args.run) if args.output is not None else None
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({"ok": False, "error_type": type(exc).__name__,
                          "original_run_unchanged": True, "no_api_calls": True}))
        return 1
    print(json.dumps({"ok": True, "archive": archive, "no_api_calls": True} if archive else result,
                     ensure_ascii=False, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
