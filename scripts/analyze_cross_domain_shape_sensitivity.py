"""Pre-test-fixed secondary shape sensitivity; never refit or recertify policies.

Motivation was discovered after validation: the unrelated arithmetic instruction
does not explicitly state nesting. This narrowly specified secondary rule was
fixed BEFORE test generation/access. Strict primary results remain authoritative
and untouched. Default stdout only; --report writes OUT/shape_sensitivity.json.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.analyze_cross_domain_mvp import (  # noqa: E402
    COMPARISONS,
    COVERAGES,
    DEFAULT_OUT,
    STRATA,
    _digest,
    compare_policies,
)
from skillopt.cross_domain.experiment import summarize_repeats  # noqa: E402


def _read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _index(rows, label):
    result = {}
    for row in rows:
        task_id = row.get("id")
        if not isinstance(task_id, str) or not task_id or task_id in result:
            raise ValueError(f"{label}: missing or duplicate task id")
        result[task_id] = row
    return result


def shape_only_correct(task: dict, rollout: dict) -> bool:
    """Only the exact seven-scalar flattening of this test control is accepted."""
    if (task.get("split") != "test" or task.get("mechanism") != "none"
            or task.get("group") != "unrelated" or rollout.get("agent_ok") is not True
            or rollout.get("hard") != 0):
        return False
    evaluation = rollout.get("evaluation", {})
    if evaluation.get("format_valid") is not True:
        return False
    gold, predicted = task.get("gold"), evaluation.get("parsed_answer")
    if (type(gold) is not list or len(gold) != 3 or type(gold[0]) is not list
            or len(gold[0]) != 5 or type(predicted) is not list):
        return False
    flattened = gold[0] + gold[1:]
    if any(type(value) not in (int, float) or not math.isfinite(value) for value in flattened):
        return False
    return len(predicted) == 7 and all(type(actual) is type(expected) and actual == expected
                                      for actual, expected in zip(predicted, flattened))


def corrected_score(task: dict, rollout: dict):
    if rollout.get("id") != task.get("id"):
        raise ValueError("Task and rollout IDs do not match")
    if rollout.get("agent_ok") is not True:
        return None
    if type(rollout.get("hard")) is not int or rollout["hard"] not in (0, 1):
        raise ValueError("Successful raw rollout needs an integer binary strict score")
    return 1 if rollout["hard"] or shape_only_correct(task, rollout) else 0


def correct_policy_rows(rows, tasks, baseline, candidate):
    """Preserve every original common-case ID and applied decision; never add rows."""
    _index(rows, "policy")
    corrected = []
    for row in rows:
        task_id = row["id"]
        if type(row.get("applied")) is not bool:
            raise ValueError("Frozen policy application must be boolean")
        task, base, guided = tasks[task_id], baseline[task_id], candidate[task_id]
        if task.get("split") != "test" or row.get("domain") != task.get("domain"):
            raise ValueError("Policy outcomes must match the frozen test task/domain")
        if base.get("agent_ok") is not True or guided.get("agent_ok") is not True:
            raise ValueError("Original common-case row contains a raw API failure")
        applied = row["applied"]
        selected = guided if applied else base
        if (row.get("baseline") != base["hard"] or row.get("current") != base["hard"]
                or row.get("candidate") != selected["hard"]):
            raise ValueError("Strict primary row does not match shared raw draws/current=base")
        base_score, selected_score = corrected_score(task, base), corrected_score(task, selected)
        corrected.append({**row, "baseline": base_score, "current": base_score,
                          "candidate": selected_score,
                          "strict_primary_scores": {key: row[key] for key in ("baseline", "current", "candidate")},
                          "shape_only_corrections": {"baseline": shape_only_correct(task, base),
                                                     "current": shape_only_correct(task, base),
                                                     "candidate": shape_only_correct(task, selected)}})
    return corrected


def _policy_metrics(repeats, tasks, mechanism):
    result = summarize_repeats(repeats, [task["id"] for task in tasks])
    result["domains"] = {
        domain: summarize_repeats([[row for row in rows if row["domain"] == domain] for rows in repeats],
                                  [task["id"] for task in tasks if task["domain"] == domain])
        for domain in ("coding", "spreadsheet", "rule_reasoning")
    }
    result["groups"] = {}
    for group in ("positive", "near_miss", "unrelated"):
        expected = [task["id"] for task in tasks
                    if ("unrelated" if task["group"] == "positive" and task["mechanism"] != mechanism
                        else task["group"]) == group]
        result["groups"][group] = summarize_repeats(
            [[row for row in rows if row["group"] == group] for rows in repeats], expected)
    return result


def analyze_shape_sensitivity(out: Path) -> dict:
    out = Path(out).resolve()
    summary, frozen = _read(out / "summary.json"), _read(out / "frozen_policies.json")
    protocol = summary["protocol"]
    if frozen.get("protocol_hash") != _digest(protocol) or set(summary["tracks"]) != set(frozen["tracks"]):
        raise ValueError("Frozen protocol/tracks do not match the primary summary")
    n_repeats = protocol["test_repeats"]
    if type(n_repeats) is not int or n_repeats < 1:
        raise ValueError("Expected a positive number of frozen generation repeats")
    # Fail closed before reading task/response data if current is not exactly base.
    for track in frozen["tracks"].values():
        if track["skill"].get("parent_content") != "":
            raise ValueError("This secondary analysis requires empty parent_content: current must equal base")
        if track["skill"].get("source_domain") != "coding":
            raise ValueError("This fixed analysis is for coding-source tracks only")
    tasks_list = _read(out / "datasets" / "test.json")
    if any(task.get("split") != "test" for task in tasks_list):
        raise ValueError("Only frozen test tasks may enter this secondary analysis")
    tasks = _index(tasks_list, "test tasks")
    base_repeats = [_index(_read(out / "rollouts" / f"test_r{repeat}_base.json"), "base rollout")
                    for repeat in range(n_repeats)]
    corrections = {"baseline": [[tid for tid in sorted(tasks)
                                  if tid in base and shape_only_correct(tasks[tid], base[tid])]
                                 for base in base_repeats], "candidates": {}}
    tracks = {}
    required_policies = {policy for _, _, left, right in COMPARISONS for policy in (left, right)}
    for skill_id, track in sorted(frozen["tracks"].items()):
        if not skill_id or Path(skill_id).name != skill_id or skill_id in {".", ".."} or "\\" in skill_id:
            raise ValueError("Unsafe frozen skill ID")
        skill = track["skill"]
        policies = summary["tracks"][skill_id]
        if required_policies - policies.keys():
            raise ValueError("Primary summary is missing a fixed comparison policy")
        candidate_repeats = [_index(_read(out / "rollouts" / f"test_r{repeat}_{skill_id}.json"), "candidate rollout")
                             for repeat in range(n_repeats)]
        corrections["candidates"][skill_id] = [[tid for tid in sorted(tasks)
                                                 if tid in rows and shape_only_correct(tasks[tid], rows[tid])]
                                                for rows in candidate_repeats]
        corrected = {}
        for policy in sorted(policies):
            if not policy or Path(policy).name != policy or policy in {".", ".."} or "\\" in policy:
                raise ValueError("Unsafe policy name")
            corrected[policy] = [correct_policy_rows(
                _read(out / "policy_outcomes" / skill_id / f"{policy}_r{repeat}.json"),
                tasks, base_repeats[repeat], candidate_repeats[repeat]) for repeat in range(n_repeats)]
        comparisons = {
            cid: {"hypothesis": hypothesis, "left_policy": left, "right_policy": right,
                  "strata": {name: compare_policies(corrected[left], corrected[right], domains=domains)
                             for name, domains in STRATA.items()}}
            for cid, hypothesis, left, right in COMPARISONS
        }
        tracks[skill_id] = {
            "strict_primary_policy_metrics": policies,
            "shape_tolerant_policy_metrics": {name: _policy_metrics(rows, tasks_list, skill["mechanism"])
                                               for name, rows in corrected.items()},
            "fixed_paired_comparisons": comparisons,
        }
    return {
        "analysis_version": "shape-sensitivity-test-only-v1", "out_directory": str(out),
        "status": "SECONDARY sensitivity only; strict primary and frozen policies unchanged",
        "timing_declaration": "Motivated after validation; this secondary rule was fixed before test generation/access.",
        "rule": "Only successful test/none/unrelated strict failures with format_valid=true and the exact type/value-preserving seven-scalar flattening of [five-item list, number, number] become correct.",
        "protocol_hash": frozen["protocol_hash"], "fixed_coverage_percentages": list(COVERAGES),
        "shape_only_raw_correction_ids_by_repeat": corrections, "tracks": tracks,
        "limitations": [
            "No gate refitting, scope recertification, content editing, policy selection, or coverage selection.",
            "No resampling or changes to primary common-case task membership or frozen applied masks.",
            "The existing strict primary scorer is not modified; arithmetic/value/type errors remain wrong.",
            "Current=base is checked explicitly; nonempty parent skills are unsupported and rejected.",
            "Fixed comparisons reuse the preregistered paired analysis: 4000 original-task cluster bootstrap draws, averaging generation repeats first.",
            "Secondary exploratory sensitivity motivated by validation, not independent confirmation of a new method or deployment-safety guarantee.",
        ],
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--report", action="store_true", help="Additionally write OUT/shape_sensitivity.json")
    args = parser.parse_args(argv)
    out = args.out if args.out.is_absolute() else REPO_ROOT / args.out
    result = analyze_shape_sensitivity(out)
    rendered = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    if args.report:
        (out / "shape_sensitivity.json").write_text(rendered, encoding="utf-8")
    print(rendered, end="")


if __name__ == "__main__":
    main()
