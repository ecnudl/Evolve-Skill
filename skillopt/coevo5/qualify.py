"""SpreadsheetBench reference qualification (registration §2.1): zero model calls.

Every case of an item submits its own reference workbook as the answer, and the frozen v7 scorer judges the item twice,
each time in a fresh scoring directory. An item qualifies when both scorings pass every case; the others are excluded
and counted by reason category. Each qualification runs in a new directory (created exclusively: an interrupted one is
never continued; its redo is a new directory). The training side runs before launch (its result is pinned in the
manifest); the test side inside the first evaluation, before any test cell is scored, once for all chains
(evaluation.py), with the owner's consent.
"""
from __future__ import annotations

import base64
from collections import Counter
from copy import deepcopy
from pathlib import Path

from skillopt.coevolution_v5.core import seal
from skillopt.continual_eval import backends
from skillopt.continual_eval.core import read_json, require, safe_path, write_json
from skillopt.validator_pilot.api import digest

from .cells import Pause, run_parallel
from .outcomes import CLEANUP, CONFIGURATION, CONFIGURATION_PREFIXES, REFERENCE_DRIFT
from .protocol import VERSION

PASSES = 2
CATEGORIES = ("reference_recalculation_failed", "reference_cache_mismatch", "read_view_unverifiable", "other")
# reasons with which the frozen recalculation checker cannot verify a recalculated workbook's read view
# (continual_eval/sheet_recalc._recalc_valid and sheet_recalc_v7)
READ_VIEW = frozenset({
    "recalculation_added_cell_content", "recalculation_array_result_unavailable", "recalculation_changed_array_range",
    "recalculation_changed_defined_names", "recalculation_changed_formula", "recalculation_changed_literal_cell",
    "recalculation_formula_text_dependency_unverified", "recalculation_invalid_workbook_structure",
    "recalculation_removed_formula", "recalculation_sheet_identity_changed", "unsupported_formula_result",
    "general_formula_read_view_unverified"})


def reference_prediction(task):
    """A delivered answer whose every case is that case's reference workbook."""
    cases = [{"status": "available", "output_base64": base64.b64encode(Path(path).read_bytes()).decode(),
              "reason": "reference_workbook"} for path in task["private"]["test_files"]]
    return {"status": "available", "output": {"code": "", "cases": cases}, "costs": {},
            "reason": "reference_as_answer"}


def category(reason):
    side, _, base = reason.partition(":")
    if reason == REFERENCE_DRIFT:
        return "reference_cache_mismatch"
    if side == "reference":
        return "read_view_unverifiable" if base in READ_VIEW else "reference_recalculation_failed"
    return "other"


def _reasons(score):
    cases = (score.get("metrics") or {}).get("cases") or []
    return [str(score.get("reason"))] + [str(c.get("reason")) for c in cases if isinstance(c, dict)]


def _check(score, label):
    """Rows 1 and 3 apply here too: a configuration error or an unconfirmed cleanup stops the qualification."""
    for reason in _reasons(score):
        if reason in CONFIGURATION or reason.startswith(CONFIGURATION_PREFIXES):
            raise Pause("configuration", reason, label)
        if reason in CLEANUP or reason.partition(":")[2] in CLEANUP:
            raise Pause("cleanup", reason, label)
    if score.get("cleanup_confirmed") is False:
        raise Pause("cleanup", "score:cleanup_unconfirmed", label)


def _passed(score):
    cases = (score.get("metrics") or {}).get("cases")
    return (score.get("status") == "pass" and isinstance(cases, list) and cases
            and all(isinstance(c, dict) and c.get("status") == "pass" for c in cases))


def _first_failure(score):
    cases = (score.get("metrics") or {}).get("cases") or []
    for case in cases:
        if isinstance(case, dict) and case.get("status") != "pass":
            return str(case.get("reason"))
    return str(score.get("reason"))


def qualify(tasks, root, runtime, *, side, native, workers):
    """Score every item's references twice in the new directory ``root``; write and return the sealed record."""
    require(side in ("train", "test") and tasks, "Qualify a nonempty training or test side")
    require(runtime.get("spreadsheet_scorer") == "qualified_lo_recalc_v7_v1", "The frozen v7 scorer is required")
    root = safe_path(root)
    root.parent.mkdir(parents=True, exist_ok=True)
    try:
        root.mkdir()
    except FileExistsError:
        raise ValueError("A qualification runs in a new directory") from None
    jobs = [(task, scoring) for task in tasks for scoring in range(PASSES)]

    def score(job):
        task, scoring = job
        request = {"benchmark": "spreadsheetbench", "qualification": side, "task_id": task["task_id"],
                   "scoring": scoring}
        position = digest(request)
        prediction = reference_prediction(task)
        context = {"artifact_dir": str(root / "host_only" / "scorer_artifacts" / position), "position": position,
                   "request": request, "prediction_hash": digest(prediction)}
        with native.hold():
            result = backends.score("spreadsheetbench", task["public"], task["private"], prediction,
                                    runtime={**deepcopy(runtime), "_score_context": context})
        write_json(root / "scores" / (position + ".json"),
                   seal({"task_id": task["task_id"], "scoring": scoring, "score": result}))
        _check(result, "%s/%s" % (task["task_id"], scoring))
        return result

    results = run_parallel(score, jobs, workers=workers)
    by_task = {}
    for (task, scoring), result in zip(jobs, results):
        by_task.setdefault(task["task_id"], [None] * PASSES)[scoring] = result
    qualified, excluded = [], {}
    for task_id, scores in sorted(by_task.items()):
        failing = [s for s in scores if not _passed(s)]
        if failing:
            excluded[task_id] = category(_first_failure(failing[0]))
        else:
            qualified.append(task_id)
    record = seal({"version": VERSION + "-sheet-qualification", "side": side, "tasks": len(by_task),
                   "qualified": qualified, "excluded": excluded,
                   "counts": {name: sum(c == name for c in excluded.values()) for name in CATEGORIES},
                   "scorings_per_item": PASSES, "model_calls": 0,
                   "scorer": runtime["spreadsheet_scorer"], "recalculation": runtime["recalculation"],
                   "task_hashes": {t["task_id"]: digest(t) for t in tasks}})
    write_json(root / "qualification.json", record)
    return record


def load(path):
    record = read_json(path, sealed=True)
    require(record["version"] == VERSION + "-sheet-qualification" and record["model_calls"] == 0,
            "Not a qualification record of this protocol")
    return record


def summary(record):
    """Counts only (no item content): what the manifest and the reports state."""
    return {"side": record["side"], "items": record["tasks"], "qualified": len(record["qualified"]),
            "excluded": dict(Counter(record["excluded"].values()))}
