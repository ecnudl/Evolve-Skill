"""Post-hoc artifact and public-guard diagnostics for a COMPLETED frozen pilot.

No model calls; original results are never replaced. The JSON output must be a
new, immutable file outside the original run directory. Normalization and the
strict public guard are separate diagnostics: the latter never sees normalized
code, hidden tests, task expected answers or oracle outcomes when deciding.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Mapping, Sequence

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from skillopt.validator_artifact_sensitivity import extract_artifact  # noqa: E402
from skillopt.validator_pilot.analysis import compare_judges, summarize_rows  # noqa: E402
from skillopt.validator_pilot.api import digest, write_immutable_json  # noqa: E402
from skillopt.validator_pilot.tasks import Task, evaluate, parse_response, validate_code  # noqa: E402

VERSION = "validator-artifact-and-public-guard-posthoc-v1"
ROW_FIELDS = (
    "id",
    "skill_version",
    "repeat",
    "origin",
    "cluster_id",
    "family",
    "split",
    "request_hash",
    "target_ok",
    "execution_ok",
    "hard",
)
FROZEN_SOURCE_REQUIREMENTS = ("skillopt/validator_pilot/tasks.py", "skillopt/validator_pilot/analysis.py")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read(path: Path, hashes: dict[str, str], run: Path) -> Any:
    body = path.read_bytes()
    hashes[str(path.relative_to(run))] = hashlib.sha256(body).hexdigest()
    return json.loads(body)


def _key(row: Mapping[str, Any]) -> tuple[str, str, int, str]:
    return row["id"], row["skill_version"], row["repeat"], row["origin"]


def _observable(row: Mapping[str, Any]) -> bool:
    return row["target_ok"] is True and row["execution_ok"] is True and isinstance(row["hard"], bool)


def _rate(n: int, d: int) -> float | None:
    return n / d if d else None


def normalize_target(row: Mapping[str, Any], task: Task) -> dict[str, Any]:
    """Execute only the unchanged extracted artifact under the existing sandbox."""
    summary = {key: copy.deepcopy(row[key]) for key in ROW_FIELDS}
    summary.update(
        original_strict_hard=row["hard"],
        original_strict_observable=_observable(row),
        original_row_sha256=digest(dict(row)),
        original_error_category=row.get("evaluation", {}).get("error_category"),
        normalized_hard=None,
        normalized_execution_ok=False,
        normalized_failure_kind=None,
        evaluation=None,
    )
    extracted = extract_artifact(row["response"])
    summary["extraction"] = {key: value for key, value in extracted.items() if key != "code"}
    if not row["target_ok"]:
        summary["normalized_failure_kind"] = "target_unavailable"
        return summary
    if not extracted["ok"]:
        summary.update(normalized_hard=False, normalized_execution_ok=True, normalized_failure_kind="unextractable")
        return summary
    evaluated = evaluate(task, {"code": extracted["code"]})
    summary["evaluation"] = evaluated
    if not evaluated.get("execution_ok") or not isinstance(evaluated.get("hard"), bool):
        summary["normalized_failure_kind"] = "reevaluation_infrastructure"
        return summary
    summary["normalized_execution_ok"] = True
    summary["normalized_hard"] = evaluated["hard"]
    if evaluated["hard"]:
        summary["normalized_failure_kind"] = "passed"
    elif not extracted["syntax_ok"]:
        summary["normalized_failure_kind"] = "python_syntax_error"
    elif evaluated.get("error_category") == "candidate_contract_violation":
        summary["normalized_failure_kind"] = "runtime_ast_contract_violation"
    else:
        summary["normalized_failure_kind"] = "behavior_or_structural_failure"
    return summary


def artifact_metrics(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    delivered = sum(row["target_ok"] for row in rows)
    original_observable = sum(row["original_strict_observable"] for row in rows)
    original_pass = sum(row["original_strict_observable"] and row["original_strict_hard"] is True for row in rows)
    normalized_observable = sum(row["normalized_hard"] is not None for row in rows)
    normalized_pass = sum(row["normalized_hard"] is True for row in rows)
    extraction_count = sum(row["target_ok"] and row["extraction"]["ok"] for row in rows)
    failure_kinds = Counter(row["normalized_failure_kind"] for row in rows)
    return {
        "n_responses": len(rows),
        "n_tasks": len({row["id"] for row in rows}),
        "n_clusters": len({row["cluster_id"] for row in rows}),
        "target_delivered": delivered,
        "target_api_errors": len(rows) - delivered,
        "original_strict_observable": original_observable,
        "original_strict_pass": original_pass,
        "original_strict_fail": original_observable - original_pass,
        "original_strict_unobservable": len(rows) - original_observable,
        "original_strict_pass_rate": _rate(original_pass, original_observable),
        "normalized_observable": normalized_observable,
        "normalized_pass": normalized_pass,
        "normalized_fail": normalized_observable - normalized_pass,
        "normalized_unobservable": len(rows) - normalized_observable,
        "normalized_pass_rate": _rate(normalized_pass, normalized_observable),
        "extraction_count": extraction_count,
        "extraction_rate_of_delivered": _rate(extraction_count, delivered),
        "syntax_valid_extracted": sum(
            row["target_ok"] and row["extraction"]["ok"] and row["extraction"]["syntax_ok"] for row in rows
        ),
        "syntax_errors": sum(
            row["target_ok"] and row["extraction"]["ok"] and not row["extraction"]["syntax_ok"] for row in rows
        ),
        "unextractable": failure_kinds["unextractable"],
        "reevaluation_infrastructure_errors": failure_kinds["reevaluation_infrastructure"],
        "runtime_ast_contract_failures": failure_kinds["runtime_ast_contract_violation"],
        "behavior_or_structural_failures": failure_kinds["behavior_or_structural_failure"],
        "failure_kinds": dict(sorted(failure_kinds.items())),
        "extraction_modes": dict(sorted(Counter(row["extraction"]["mode"] or "unextractable" for row in rows).items())),
        "denominators": {
            "original_strict_pass_rate": original_observable,
            "normalized_pass_rate": normalized_observable,
            "extraction_rate_of_delivered": delivered,
        },
    }


def summarize_artifacts(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    output = {}
    for origin in ("natural", "controlled"):
        selected = [row for row in rows if row["origin"] == origin]
        groups: dict[str, dict[str, list[Mapping[str, Any]]]] = defaultdict(lambda: defaultdict(list))
        for row in selected:
            groups[row["split"]][row["skill_version"]].append(row)
        output[origin] = {
            "all": artifact_metrics(selected),
            "by_split": {
                split: artifact_metrics([row for row in selected if row["split"] == split]) for split in sorted(groups)
            },
            "by_split_and_skill": {
                split: {skill: artifact_metrics(values) for skill, values in sorted(versions.items())}
                for split, versions in sorted(groups.items())
            },
        }
    return output


def public_guard(row: Mapping[str, Any]) -> dict[str, Any]:
    """Deterministic schema/syntax/AST guard; no task or oracle is consulted.

    ``hard`` and other provenance fields are copied solely for later descriptive
    evaluation; neither is read to decide whether to force fail.
    """
    guarded = {key: copy.deepcopy(row[key]) for key in ROW_FIELDS}
    guarded.update(
        judge_ok=row["judge_ok"],
        judgment=copy.deepcopy(row.get("judgment")),
        original_judgment=copy.deepcopy(row.get("judgment")),
        original_judge_ok=row["judge_ok"],
        public_guard_forced=False,
        guard_reason=None,
        guard_source="strict_schema_syntax_AST_only",
        judge_request_hash=row.get("judge_request_hash"),
        validator_arm=row.get("validator_arm"),
        original_response_sha256=hashlib.sha256(row["response"].encode()).hexdigest(),
    )
    if not row["target_ok"]:
        guarded["guard_reason"] = "target_unavailable_no_artifact_guard"
        return guarded
    try:
        code = parse_response(row["response"])
    except (TypeError, ValueError) as exc:
        reason = "response_schema:" + type(exc).__name__
    else:
        try:
            validate_code(code)
        except SyntaxError:
            reason = "python_syntax:SyntaxError"
        except (TypeError, ValueError) as exc:
            reason = "runtime_AST_contract:" + type(exc).__name__
        else:
            return guarded
    guarded.update(
        judgment={"decision": "fail", "schema_valid": True},
        judge_ok=True,
        public_guard_forced=True,
        guard_reason=reason,
        judgment_source="deterministic_public_guard_not_LLM",
    )
    return guarded


def _validate_source_hashes(protocol: Mapping[str, Any]) -> dict[str, Any]:
    registered = protocol.get("source_hashes")
    if not isinstance(registered, dict):
        raise ValueError("protocol lacks registered source hashes")
    checks = {}
    for relative in FROZEN_SOURCE_REQUIREMENTS:
        path = REPO / relative
        expected = registered.get(relative)
        if not isinstance(expected, str) or digest(path.read_text(encoding="utf-8")) != expected:
            raise ValueError("current evaluator/analysis differs from frozen source")
        checks[relative] = {"registered_digest": expected, "raw_file_sha256": _sha(path), "matches": True}
    return checks


def analyze_run(run: Path, output: Path) -> dict[str, Any]:
    run, output = Path(run).resolve(), Path(output).resolve()
    if output == run or run in output.parents:
        raise ValueError("output must be a new JSON report outside the original run")
    if output.exists() and not output.is_file():
        raise ValueError("output must be a JSON file, not a directory")
    hashes: dict[str, str] = {}
    # This is intentionally the FIRST experiment-data read. Incomplete runs may
    # contain held-out answers, but this CLI must not inspect them yet.
    results_path = run / "results.json"
    if not results_path.is_file():
        raise ValueError("completed results.json is required before sensitivity analysis")
    results = _read(results_path, hashes, run)
    if not isinstance(results, dict) or results.get("status") != "complete":
        raise ValueError("run status must be complete")
    protocol = _read(run / "protocol.json", hashes, run)
    source_checks = _validate_source_hashes(protocol)
    _read(run / "rubrics_frozen.json", hashes, run)
    serialized_tasks = _read(run / "tasks_private.json", hashes, run)
    if not isinstance(serialized_tasks, dict) or digest(serialized_tasks) != protocol.get("task_manifest_hash"):
        raise ValueError("task manifest does not match the frozen protocol")
    tasks = {identifier: Task.from_dict(value) for identifier, value in serialized_tasks.items()}
    if any(identifier != task.id for identifier, task in tasks.items()):
        raise ValueError("task manifest identity mismatch")
    targets = _read(run / "targets_frozen_private.json", hashes, run)
    if not isinstance(targets, list):
        raise ValueError("frozen targets must be a list")
    indexed = {}
    normalized = []
    for row in targets:
        if any(type(row.get(field)) is not bool for field in ("target_ok", "execution_ok")):
            raise ValueError("target delivery/execution flags must be explicit booleans")
        if row.get("hard") is not None and type(row["hard"]) is not bool:
            raise ValueError("target hard result must be boolean or unavailable None")
        if type(row.get("repeat")) is not int or row["repeat"] < 0:
            raise ValueError("target repeat must be a nonnegative integer")
        if not isinstance(row.get("request_hash"), str) or not row["request_hash"]:
            raise ValueError("target request hash must be explicit")
        key = _key(row)
        if key in indexed or row["id"] not in tasks or row["origin"] not in ("natural", "controlled"):
            raise ValueError("duplicate/invalid target identity")
        task = tasks[row["id"]]
        if any(row[field] != getattr(task, field) for field in ("split", "family", "cluster_id")):
            raise ValueError("target grouping differs from frozen task")
        if not isinstance(row.get("response"), str):
            raise ValueError("target response must be explicit string")
        indexed[key] = row
        normalized.append(normalize_target(row, task))

    holdout_paths = sorted((run / "holdout").glob("*.json"))
    if not holdout_paths or set(path.stem for path in holdout_paths) != set(results.get("holdout", {})):
        raise ValueError("held-out arm files do not match completed results")
    original, guarded, within_arm = {}, {}, {}
    for path in holdout_paths:
        rows = _read(path, hashes, run)
        for row in rows:
            target = indexed.get(_key(row))
            if target is None or row.get("split") != "holdout":
                raise ValueError("held-out judgment lacks frozen held-out target")
            if any(row.get(field) != target.get(field) for field in (*ROW_FIELDS, "response")):
                raise ValueError("held-out judgment changed frozen target evidence")
        guarded_rows = [public_guard(row) for row in rows]
        original[path.stem] = rows
        guarded[path.stem] = guarded_rows
        within_arm[path.stem] = compare_judges(rows, guarded_rows)

    script_files = [
        Path(__file__).resolve(),
        REPO / "skillopt/validator_artifact_sensitivity.py",
        REPO / "skillopt/validator_pilot/tasks.py",
        REPO / "skillopt/validator_pilot/analysis.py",
        REPO / "skillopt/validator_pilot/api.py",
    ]
    report = {
        "version": VERSION,
        "status": "complete",
        "input_run": str(run),
        "classification": "POSTHOC engineering diagnostic, not independent confirmation",
        "model_calls": 0,
        "original_protocol_replaced": False,
        "original_results_edited": False,
        "artifact_normalization": {
            "by_origin": summarize_artifacts(normalized),
            "rows": normalized,
            "interpretation": "Same frozen response content; no quote/syntax/logic repair. Unextractable delivered artifacts count as normalized failures; infrastructure remains None.",
        },
        "strict_public_guard": {
            "by_arm": {arm: summarize_rows(rows) for arm, rows in guarded.items()},
            "original_by_arm": {arm: summarize_rows(rows) for arm, rows in original.items()},
            "within_arm_paired": within_arm,
            "between_arms_guarded": {
                arm: compare_judges(guarded["static_v0"], rows) for arm, rows in guarded.items() if arm != "static_v0"
            }
            if "static_v0" in guarded
            else {},
            "forced_counts": {arm: sum(row["public_guard_forced"] for row in rows) for arm, rows in guarded.items()},
            "rows": guarded,
            "interpretation": "Original strict truth retained. Guard uses only parse_response and validate_code; no normalization, hidden tests, oracle, or task answers. Original judgment and judge_ok retained per row. Deterministic forced fails are not successful LLM judgments.",
        },
        "provenance": {
            "input_artifact_sha256": hashes,
            "protocol_sha256": hashes["protocol.json"],
            "source_files_sha256": {str(path.relative_to(REPO)): _sha(path) for path in script_files},
            "frozen_source_checks": source_checks,
        },
        "limitations": [
            "Post-hoc diagnostics were designed after observing training-format failures; not a new confirmatory benchmark.",
            "Natural and deliberately controlled artifacts are reported separately; repeated draws and fixtures are not independent projects.",
            "Normalization changes delivery acceptance only, not candidate behavior; original strict results remain authoritative for the frozen protocol.",
            "The strict guard can reject invalid delivery even when extracted behavior would be correct; guard and normalization answer different questions.",
            "No new model calls; this analysis does not demonstrate actual API-cost savings or a deployed guard.",
            "Hard checks are finite behavior/structure checks under the original restricted sandbox, not proof of general correctness.",
        ],
    }
    write_immutable_json(output, report)
    return report


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True, type=Path, help="Original completed frozen run")
    parser.add_argument("--output", required=True, type=Path, help="New immutable JSON report OUTSIDE the original run")
    args = parser.parse_args(argv)
    try:
        report = analyze_run(args.run, args.output)
    except Exception as exc:
        print(json.dumps({"status": "refused", "error_type": type(exc).__name__, "no_original_results_edited": True}))
        return 2
    print(
        json.dumps(
            {
                "status": "complete",
                "output": str(args.output.resolve()),
                "n_artifacts": len(report["artifact_normalization"]["rows"]),
                "model_calls": 0,
                "posthoc_only": True,
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
