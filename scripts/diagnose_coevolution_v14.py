"""Completed-only, read-only diagnostics of actual V14 learning evidence.

No new inference, optimization, candidate execution, model calls or file writes.
Authored mutant calibration is explicitly separate from actual model probes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from scripts.coevolution_v14 import completed_replay, study_module  # noqa: E402
from scripts.report_coevolution_v14 import _delivery_summary, _learning_rows  # noqa: E402
from skillopt.coevolution_v12.analysis import _score  # noqa: E402
from skillopt.validator_pilot.api import digest  # noqa: E402

EMPTY_HASH = hashlib.sha256(b"").hexdigest()
CLASSES = ("pass", "oracle_evaluated_failure", "delivery_api_unavailable", "delivery_invalid",
           "delivered_oracle_unknown")


def _class(score, api_available=True):
    if score["oracle_available"]:
        return "pass" if score["semantic_success"] else "oracle_evaluated_failure"
    if score["delivery_valid"]:
        return "delivered_oracle_unknown"
    return "delivery_invalid" if api_available else "delivery_api_unavailable"


def _counts(rows):
    counts = dict.fromkeys(CLASSES, 0)
    for row in rows:
        counts[row["failure_class"]] += 1
    return {"unique_observations": len(rows), **counts,
            "oracle_unknown": sum(not r["score"]["oracle_available"] for r in rows),
            "api_not_ok_either_stage": sum(r.get("api_ok") is False for r in rows)}


def _solves(root, result):
    indexed, requests = {}, set()
    for path in sorted((root / "runtime/solves").glob("*.json")):
        raw = study_module().read(path)
        if (path.stem != digest(raw["identity"]) or raw["record_hash"] in indexed
                or raw["phase"] not in {"development", "final"}):
            raise ValueError("Invalid/duplicate actual solver identity")
        key = tuple(raw["request_hashes"])
        if len(key) != 2 or len(set(key)) != 2 or key in requests:
            raise ValueError("Duplicate or incomplete actual solver requests")
        requests.add(key)
        score = _score(raw["score"])
        chosen = {"generation": 0, "revision": 1}[raw["chosen_stage"]]
        if len(raw["stage_api_ok"]) != 2 or any(type(v) is not bool for v in raw["stage_api_ok"]):
            raise ValueError("Explicit generation and revision availability required")
        indexed[raw["record_hash"]] = {
            "task_id": raw["task_id"], "task_hash": raw["identity"]["task_hash"],
            "artifact_hash": digest(raw["artifact"]), "history": raw["identity"]["repeat"],
            "domain": raw["domain"], "phase": raw["phase"], "skill_hash": raw["skill_hash"],
            "score": score, "api_ok": all(raw["stage_api_ok"]),
            "failure_class": _class(score, raw["stage_api_ok"][chosen])}
    if len(indexed) != result["evidence_closure"]["unique_trajectories"]:
        raise ValueError("Actual solver count differs from completed closure")
    return indexed


def _learning(root, protocol, result):
    projected, references = [], defaultdict(set)
    for row in _learning_rows(root, protocol, result):
        key = f"h{row['history']}-r{row['round']}-{row['arm']}"
        raw = study_module().read(root / "learning" / (key + ".json"))
        if raw["skill_hash"] != hashlib.sha256(raw["skill"].encode()).hexdigest():
            raise ValueError("Learning Skill text hash mismatch")
        projected.append({**row, "skill_chars": len(raw["skill"]), "nonempty_skill": bool(raw["skill"])})
        for probe in raw["probe_hashes"]:
            if row["arm"] != "constrained":
                raise ValueError("Unexpected extra-probe evidence in independent arm")
            references[probe].add((row["history"], row["round"]))
    return projected, references


def _behavior(raw):
    """An input_unchanged success NEVER substitutes for an obligation's behavior."""
    score = _score(raw["score"])
    mapping = raw["case_obligations"]
    if (not isinstance(mapping, dict) or not mapping
            or any(type(k) is not str or type(v) is not str or not k or not v for k, v in mapping.items())):
        raise ValueError("Explicit probe-case to obligation mapping required")
    indexed = {}
    if score["oracle_available"]:
        for row in raw["evaluation"].get("case_results", []):
            if row["id"] in indexed or type(row.get("passed")) is not bool:
                raise ValueError("Duplicate or non-Boolean actual probe case")
            indexed[row["id"]] = row["passed"]
        expected = ({case + ":" + suffix for case in mapping for suffix in ("behavior", "input_unchanged")}
                    if raw["domain"] == "coding" else set(mapping))
        if set(indexed) != expected:
            raise ValueError("Available probe requires the complete actual behavior grid")
    outcomes, preservation = [], dict.fromkeys(("pass", "fail", "unknown"), 0)
    for case, obligation in mapping.items():
        name = case + ":behavior" if raw["domain"] == "coding" else case
        passed = indexed.get(name)
        status = "unknown" if passed is None else "pass" if passed else "fail"
        outcomes.append((obligation, status))
        if raw["domain"] == "coding":
            kept = indexed.get(case + ":input_unchanged")
            preservation["unknown" if kept is None else "pass" if kept else "fail"] += 1
    return outcomes, preservation


def _probes(root, indexed, references, result):
    by_domain, obligations, preservation = defaultdict(list), defaultdict(dict), defaultdict(lambda: dict.fromkeys(("pass", "fail", "unknown"), 0))
    by_source = defaultdict(list)
    for identifier, solve in indexed.items():
        if solve["phase"] == "development":
            by_source[solve["task_id"], solve["task_hash"], solve["artifact_hash"]].append((identifier, solve))
    seen, executions, novelty = set(), set(), defaultdict(lambda: {
        "ordinary_pass_probe_fail": 0, "ordinary_fail_probe_fail": 0,
        "ordinary_unknown_probe_fail": 0, "probe_unknown": 0,
        "no_skill_ordinary_pass_probe_fail": 0, "skill_ordinary_pass_probe_fail": 0,
        "ordinary_pass_probe_behavior_failure": 0, "ordinary_pass_preservation_only_failure": 0})
    for path in sorted((root / "runtime/probes/solves").glob("*.json")):
        raw = study_module().read(path)
        identifier = raw["record_hash"]
        if (path.stem != digest(raw["identity"]) or raw["phase"] != "development" or raw["probe"] is not True
                or identifier in seen or raw["execution_id"] in executions or identifier not in references):
            raise ValueError("Probe is not unique closed development evidence")
        seen.add(identifier)
        executions.add(raw["execution_id"])
        matched = []
        for solve_hash, solve in by_source[raw["source_task_id"], raw["source_task_hash"], raw["artifact_hash"]]:
            for history, round_index in references[identifier]:
                expected = digest({"solve_hash": solve_hash, "history": history, "round": round_index,
                                   "probe_task_hash": raw["task_hash"]})
                if expected == raw["key"] and solve["history"] == history and solve["domain"] == raw["domain"]:
                    matched.append(solve)
        if len(matched) != 1:
            raise ValueError("Actual probe lacks one exact model-solve/history provenance")
        source, domain, score = matched[0], raw["domain"], _score(raw["score"])
        novelty[domain]  # Include explicit zero counts for domains whose probes all pass.
        row = {"score": score, "failure_class": _class(score)}
        by_domain[domain].append(row)
        outcomes, kept = _behavior(raw)
        for obligation, status in outcomes:
            obligations[domain].setdefault(obligation, dict.fromkeys(("pass", "fail", "unknown"), 0))[status] += 1
        for name, count in kept.items():
            preservation[domain][name] += count
        if not score["oracle_available"]:
            novelty[domain]["probe_unknown"] += 1
        elif score["semantic_success"] == 0:
            ordinary = source["score"]
            label = "unknown" if not ordinary["oracle_available"] else "pass" if ordinary["semantic_success"] else "fail"
            novelty[domain][f"ordinary_{label}_probe_fail"] += 1
            if label == "pass":
                prefix = "no_skill" if source["skill_hash"] == EMPTY_HASH else "skill"
                novelty[domain][prefix + "_ordinary_pass_probe_fail"] += 1
                if any(status == "fail" for _, status in outcomes):
                    novelty[domain]["ordinary_pass_probe_behavior_failure"] += 1
                elif kept["fail"]:
                    novelty[domain]["ordinary_pass_preservation_only_failure"] += 1
    if (seen != set(references) or len(seen) != result["evidence_closure"]["extra_probe_native_evaluations"]):
        raise ValueError("Actual model probes do not close against learning evidence")
    return {"unique_model_artifact_evaluations": len(seen),
        "by_domain": {domain: _counts(rows) for domain, rows in sorted(by_domain.items())},
        "obligation_behavior_by_domain": dict(obligations),
        "input_preservation_separate_not_obligation_behavior": dict(preservation),
        "extra_cases_vs_ordinary_development": dict(novelty),
        "mutant_calibration_not_included": True,
        "unknown_cases_never_counted_as_semantic_pass_or_failure": True,
        "obligation_labels_are_probe_intent_not_proven_causal_mechanism": True,
        "counts_are_repeated_observations_not_independent_effect_estimates": True}


def _calibration(root, protocol):
    expected = protocol.get("task_preflight_hash")
    if expected is None:
        return {"available": False, "is_actual_model_error_evidence": False}
    raw = study_module().read(root / "task_preflight.json")
    if raw["record_hash"] != expected:
        raise ValueError("Calibration evidence differs from frozen protocol")
    return {"available": True, "checked_tasks": raw["checked_tasks"],
        "checked_probe_tasks": raw["checked_probe_tasks"],
        "checked_obligation_mutants": raw["checked_obligation_mutants"],
        "is_actual_model_error_evidence": False}


def diagnose(output, *, repo=REPO):
    with completed_replay(repo, output) as audited:
        root, protocol, result = (audited[k] for k in ("root", "protocol", "result"))
        solves = _solves(root, result)
        learning, references = _learning(root, protocol, result)
        development = [r for r in solves.values() if r["phase"] == "development"]
        output = {"version": "v14-completed-actual-evidence-diagnostic-v1", "complete": True,
            "design": protocol["design"], "result_hash": result["record_hash"],
            "posthoc_descriptive_only": True, "new_primary_inference": False,
            "development_actual_solver": {"overall": _counts(development),
                "by_domain": {d: _counts([r for r in development if r["domain"] == d])
                              for d in sorted({r["domain"] for r in development})},
                "unique_trajectories_not_role_or_policy_aliases": True,
                "api_failure_does_not_force_semantic_unknown_after_delivery_rollback": True},
            "actual_model_probes": _probes(root, solves, references, result),
            "authored_calibration_separate": _calibration(root, protocol),
            "learning_updates": learning,
            "final_delivery_only": _delivery_summary(root, result),
            "model_api_calls": 0, "native_executions": 0, "files_written": 0,
            "run_files_unchanged": True,
            "no_task_skill_reference_or_response_bodies_in_output": True}
    return output


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    print(json.dumps(diagnose(args.output), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
