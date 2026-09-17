"""Post-hoc, validation-only audit of one narrowly defined JSON-shape ambiguity.

Reads saved validation data/outcomes only: no API, task generation, routing,
selection, gate invocation, or test-file access. Original hard scores remain the
primary result. The additional score accepts exactly nine differences followed
by the two summary numbers as a flat array instead of [differences, sum, count].
It never repairs numeric errors, ordering, invalid JSON, or API failures.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from collections import defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

_DEFAULT_RUN = "outputs/cross_domain/scope_mvp_gpt55_20260907"
_CANDIDATE_FILE = re.compile(r"validation_(?:constraint_preservation|evidence_verification)_v\d+\.json")
_NOTES = [
    "Post-hoc validation diagnostic only; original strict hard scores remain authoritative primary results.",
    "This report does not refit scope, reselect skills, change thresholds, rerun a gate, or authorize deployment.",
    "Only validation/none/unrelated rows with valid JSON and an exactly matching 11-element flattening qualify.",
    "Exact numeric equality follows the primary scorer: finite 1 and 1.0 are equivalent; booleans are not numbers.",
    "Invalid JSON, extra output fields, API failures, wrong numbers, and other task families remain failures.",
    "No test dataset or test outcome file is read. A future test sensitivity must be specified separately before viewing test results.",
    "Paired comparisons use only task IDs with successful API outcomes in both arms; exclusions are reported.",
]


def _exact_json(left: Any, right: Any) -> bool:
    """Exact JSON value equality with no float tolerance or bool/int coercion."""
    if isinstance(left, bool) or isinstance(right, bool):
        return type(left) is type(right) and left == right
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return math.isfinite(left) and math.isfinite(right) and left == right
    if type(left) is not type(right):
        return False
    if isinstance(left, list):
        return len(left) == len(right) and all(_exact_json(a, b) for a, b in zip(left, right))
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(_exact_json(left[key], right[key]) for key in left)
    return left == right


def _flattened_gold(gold: Any) -> list[Any] | None:
    if not isinstance(gold, list) or len(gold) != 3 or not isinstance(gold[0], list) or len(gold[0]) != 9:
        return None
    values = gold[0] + gold[1:]
    if any(isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) for value in values):
        return None
    return values


def normalization(task: Mapping[str, Any], row: Mapping[str, Any]) -> dict[str, Any]:
    """Return an annotation, never a modified task/outcome or replacement score.

    This version deliberately recognizes only the validation nine-difference
    family. The pure exact-comparison helpers can support a separately declared
    future sensitivity, but this function cannot normalize test examples.
    """
    for field in ("id", "domain", "mechanism", "group", "split"):
        if row.get(field) != task.get(field):
            raise ValueError(f"Outcome/dataset mismatch for {field}: {row.get('id')!r}")
    if not isinstance(row.get("agent_ok"), bool):
        raise ValueError("agent_ok must be a boolean")
    request_hash = row.get("request_hash")
    if not isinstance(request_hash, str) or not request_hash:
        raise ValueError("A request_hash is required for traceability")
    successful = row["agent_ok"]
    hard = row.get("hard")
    if successful and (isinstance(hard, bool) or not isinstance(hard, (int, float)) or hard not in (0, 1)):
        raise ValueError("Successful outcomes must retain a binary primary hard score")
    evaluation = row.get("evaluation")
    if not isinstance(evaluation, Mapping):
        raise ValueError("Saved evaluation is required; raw output is never reparsed here")
    if successful and evaluation.get("correct") is not bool(hard):
        raise ValueError("Saved primary hard score contradicts evaluation.correct")
    strict = successful and hard == 1
    flattened = _flattened_gold(task.get("gold"))
    eligible = (task.get("split") == "validation" and task.get("mechanism") == "none"
                and task.get("group") == "unrelated" and evaluation.get("format_valid") is True)
    shape_only = (successful and not strict and eligible and flattened is not None
                  and _exact_json(evaluation.get("parsed_answer"), flattened))
    annotation = {
        **{field: task[field] for field in ("id", "domain", "mechanism", "group", "split")},
        "request_hash": request_hash,
        "agent_ok": successful,
        "original_hard": hard,
        "strict_correct": bool(strict),
        "shape_only": bool(shape_only),
        "shape_tolerant_correct": bool(strict or shape_only),
    }
    if shape_only:
        annotation.update({"gold_nested": task["gold"], "parsed_answer": evaluation["parsed_answer"],
                           "reason": "exact_flattening_of_nine_differences_and_two_summaries"})
    return annotation


def _counts(rows: Sequence[Mapping[str, Any]], expected_n: int | None = None) -> dict[str, Any]:
    successful = sum(row["agent_ok"] for row in rows)
    strict = sum(row["strict_correct"] for row in rows)
    shape_only = sum(row["shape_only"] for row in rows)
    return {
        "n_saved": len(rows), "n_expected": len(rows) if expected_n is None else expected_n,
        "n_missing": 0 if expected_n is None else expected_n - len(rows),
        "n_api_success": successful, "n_api_error": len(rows) - successful,
        "strict_correct": strict, "shape_only": shape_only, "shape_tolerant_correct": strict + shape_only,
        "strict_em_on_api_success": strict / successful if successful else None,
        "shape_tolerant_em_on_api_success": (strict + shape_only) / successful if successful else None,
    }


def _paired_counts(pairs: Sequence[tuple[Mapping[str, Any], Mapping[str, Any]]], score: str) -> dict[str, Any]:
    wins = sum(not base[score] and candidate[score] for base, candidate in pairs)
    losses = sum(base[score] and not candidate[score] for base, candidate in pairs)
    return {
        "wins": wins, "losses": losses, "ties": len(pairs) - wins - losses,
        "both_correct": sum(base[score] and candidate[score] for base, candidate in pairs),
        "both_wrong": sum(not base[score] and not candidate[score] for base, candidate in pairs),
        "net_improvement": wins - losses, "delta_em": (wins - losses) / len(pairs) if pairs else None,
    }


def _pair_audit(base_rows: list[dict], candidate_rows: list[dict], expected_n: int) -> dict[str, Any]:
    base, candidate = ({row["id"]: row for row in records} for records in (base_rows, candidate_rows))
    ids = sorted(task_id for task_id in base.keys() & candidate.keys()
                 if base[task_id]["agent_ok"] and candidate[task_id]["agent_ok"])
    pairs = [(base[task_id], candidate[task_id]) for task_id in ids]
    cells = defaultdict(list)
    for pair in pairs:
        row = pair[0]
        cells[row["domain"], row["mechanism"], row["group"]].append(pair)
    changes = []
    for b, c in pairs:
        strict_delta = int(c["strict_correct"]) - int(b["strict_correct"])
        tolerant_delta = int(c["shape_tolerant_correct"]) - int(b["shape_tolerant_correct"])
        if strict_delta or tolerant_delta or b["shape_only"] or c["shape_only"]:
            changes.append({"id": b["id"], "domain": b["domain"], "mechanism": b["mechanism"], "group": b["group"],
                            "baseline_request_hash": b["request_hash"], "candidate_request_hash": c["request_hash"],
                            "baseline_strict": b["strict_correct"], "candidate_strict": c["strict_correct"],
                            "baseline_shape_only": b["shape_only"], "candidate_shape_only": c["shape_only"],
                            "strict_delta": strict_delta, "shape_tolerant_delta": tolerant_delta})
    return {
        "n_paired_api_success": len(pairs), "n_excluded_missing_or_api_error": expected_n - len(pairs),
        "strict": _paired_counts(pairs, "strict_correct"),
        "shape_tolerant": _paired_counts(pairs, "shape_tolerant_correct"),
        "cells": [{"domain": domain, "mechanism": mechanism, "group": group, "n_pairs": len(values),
                   "strict": _paired_counts(values, "strict_correct"),
                   "shape_tolerant": _paired_counts(values, "shape_tolerant_correct")}
                  for (domain, mechanism, group), values in sorted(cells.items())],
        "changed_or_shape_affected_pairs": changes,
    }


def audit_run(run_dir: Path, candidate_ids: Sequence[str] | None = None) -> dict[str, Any]:
    """Read only fixed validation paths and return a JSON-serializable audit."""
    root = Path(run_dir).resolve()
    sources = []

    def read(path: Path) -> Any:
        raw = path.read_bytes()
        sources.append({"path": str(path.relative_to(root)), "sha256": hashlib.sha256(raw).hexdigest()})
        return json.loads(raw)

    tasks = read(root / "datasets" / "validation.json")
    if not isinstance(tasks, list) or any(not isinstance(task, dict) or task.get("split") != "validation" for task in tasks):
        raise ValueError("Only a validation dataset is permitted")
    task_lookup = {task["id"]: task for task in tasks}
    if len(task_lookup) != len(tasks):
        raise ValueError("Duplicate validation task IDs")
    expected_cells = defaultdict(int)
    for task in tasks:
        expected_cells[task["domain"], task["mechanism"], task["group"]] += 1
    paths = [root / "rollouts" / "validation_base.json"]
    if candidate_ids is None:
        paths += sorted(path for path in (root / "rollouts").glob("validation_*.json") if _CANDIDATE_FILE.fullmatch(path.name))
    else:
        if len(set(candidate_ids)) != len(candidate_ids):
            raise ValueError("Duplicate candidate IDs")
        for identifier in candidate_ids:
            if not _CANDIDATE_FILE.fullmatch(f"validation_{identifier}.json"):
                raise ValueError("Candidate IDs must be constraint_preservation_vN or evidence_verification_vN")
            paths.append(root / "rollouts" / f"validation_{identifier}.json")
    arms = {}
    for path in paths:
        records = read(path)
        if not isinstance(records, list):
            raise ValueError("Saved rollouts must be a list")
        seen, annotations = set(), []
        for row in records:
            task_id = row["id"]
            if task_id in seen or task_id not in task_lookup:
                raise ValueError("Duplicate or out-of-dataset rollout task ID")
            seen.add(task_id)
            annotations.append(normalization(task_lookup[task_id], row))
        cells = defaultdict(list)
        for row in annotations:
            cells[row["domain"], row["mechanism"], row["group"]].append(row)
        arms[path.stem.removeprefix("validation_")] = {
            **_counts(annotations, len(tasks)),
            "cells": [{"domain": domain, "mechanism": mechanism, "group": group,
                       **_counts(cells[domain, mechanism, group], n)}
                      for (domain, mechanism, group), n in sorted(expected_cells.items())],
            "rows": annotations,
        }
    return {
        "audit_version": "validation-shape-only-v1", "evaluation_split": "validation",
        "diagnostic_only": True, "primary_scores_unchanged": True, "gate_recomputed": False,
        "test_read": False, "run_dir": str(root), "input_sources": sources, "notes": list(_NOTES),
        "arms": arms,
        "forced_candidate_vs_base": {
            name: _pair_audit(arms["base"]["rows"], values["rows"], len(tasks))
            for name, values in arms.items() if name != "base"
        },
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, default=Path(_DEFAULT_RUN))
    parser.add_argument("--candidate-id", action="append", help="Optional explicit candidate ID; repeat for multiple arms")
    parser.add_argument("--report", action="store_true", help="Create validation_shape_audit.json in the run directory; never overwrite")
    args = parser.parse_args(argv)
    report = audit_run(args.run_dir, args.candidate_id)
    payload = json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    if args.report:
        destination = args.run_dir.resolve() / "validation_shape_audit.json"
        # Exclusive create: no original artifact (or prior diagnostic) is overwritten.
        with destination.open("x", encoding="utf-8") as stream:
            stream.write(payload)
        print(json.dumps({"report": str(destination), "diagnostic_only": True,
                          "arms": {name: {key: value for key, value in arm.items() if key not in {"rows", "cells"}}
                                   for name, arm in report["arms"].items()}}, ensure_ascii=False))
    else:
        print(payload, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
