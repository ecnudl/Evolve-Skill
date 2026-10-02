"""Opt-in, host-only production adapter for the qualified v5 Calc scorer.

This does not enable Spreadsheet learning or change any historical score.
Qualification is path/source-bound; a new frozen source tree needs its own
zero-model-call qualification. Reference workbooks never enter solver storage.
"""
from __future__ import annotations

import base64
import hashlib
import tempfile
import zipfile
from collections import Counter
from pathlib import Path

from skillopt.coevolution_v5.core import seal
from skillopt.validator_pilot.api import digest

from . import sheet_recalc as recalc
from .core import output_lock, read_json, require, safe_path, write_json

VERSION = "qualified_lo_recalc_v5_v1"
CONTROLS = frozenset({"correct", "wrong", "empty_string", "retained_dependency", "unsupported",
    "array_correct", "array_wrong", "numeric_roundtrip", "numeric_wrong", "boolean_false", "boolean_true",
    "boolean_wrong", "boolean_string_wrong", "utf16le_metadata", "utf16be_metadata", "utf16_external", "utf16_doctype"})


def qualified_engine(runtime):
    """Validate the complete authorization without starting any container."""
    require(runtime.get("spreadsheet_scorer") == VERSION, "Explicit recalculation profile required")
    spec = runtime.get("recalculation")
    require(type(spec) is dict and set(spec) == {"image", "timeout_seconds", "qualification_path",
                                               "qualification_sha256", "qualification_hash"},
            "Invalid recalculation configuration")
    require(type(spec["qualification_path"]) is str and Path(spec["qualification_path"]).is_absolute(),
            "Absolute qualification path required")
    path = safe_path(spec["qualification_path"])
    require(recalc.sha(path) == spec["qualification_sha256"], "Qualification file changed")
    qualified = read_json(path, sealed=True)
    engine = recalc.Recalculator(spec["image"], spec["timeout_seconds"])
    require(qualified["record_hash"] == spec["qualification_hash"] and qualified["version"] == recalc.VERSION
            and qualified["status"] == "qualified" and qualified["engine"] == engine.identity
            and qualified["model_api_calls"] == 0 and qualified["evidence_kind"] == "engineering_fixture",
            "Qualification authorization/source/image differs")
    controls = qualified["controls"]
    require(len(controls) == len(CONTROLS) and {c["name"] for c in controls} == CONTROLS
            and all(c["qualified"] is True and c["cleanup_confirmed"] is True for c in controls),
            "Complete successful qualification controls required")
    for control in controls:
        receipt = read_json(path.parent / "receipts" / (control["name"] + ".json"), sealed=True)
        require(receipt["record_hash"] == control["receipt_hash"] and receipt["identity"] == engine.identity
                and receipt["cleanup_confirmed"] is True and receipt["model_api_calls"] == 0,
                "Qualification receipt binding differs")
    return engine, qualified


def readiness(runtime):
    from .backends import _image_ready

    try:
        engine, _ = qualified_engine(runtime)
    except (OSError, ValueError, KeyError, TypeError):
        return {"status": "unsupported", "reason": "invalid_recalculation_qualification"}
    return _image_ready({"image": engine.image})


def _context(runtime, public, private, prediction, qualified):
    context = runtime.get("_score_context")
    require(type(context) is dict and set(context) == {"artifact_dir", "position", "request", "prediction_hash"},
            "Host-only score context required")
    require(context["request"]["benchmark"] == "spreadsheetbench"
            and digest(context["request"]) == context["position"], "Scorer position binding differs")
    root = safe_path(context["artifact_dir"])
    require(root.name == context["position"] and root.parent.name == "scorer_artifacts"
            and root.parent.parent.name == "host_only", "Private evidence must use host-only scorer storage")
    binding = seal({"version": VERSION, "position": context["position"], "request": context["request"],
        "prediction_hash": context["prediction_hash"], "prediction_value_hash": digest(prediction),
        "public_hash": digest(public), "private_hash": digest(private),
        "qualification_hash": qualified["record_hash"], "engine": qualified["engine"]})
    return root, binding


def score(public, private, prediction, *, runtime, replay_only=False):
    engine, qualified = qualified_engine(runtime)
    root, binding = _context(runtime, public, private, prediction, qualified)
    references = private["test_files"]
    require(type(references) is list and references, "Reference cases required")
    # Recheck assets immediately before execution/replay, not just plan loading.
    for reference in references:
        require(private.get("asset_sha256", {}).get(reference) == recalc.sha(reference), "Reference asset changed")
    root.mkdir(parents=True, mode=0o700, exist_ok=True)
    with output_lock(root):
        if (root / "result.json").is_file():
            saved = read_json(root / "result.json", sealed=True)
            require(saved["binding"] == binding, "Scorer result belongs to another position/prediction")
            require(all(recalc.sha(root / name) == expected for name, expected in saved["artifacts"].items()),
                    "Scorer evidence changed")
            return saved["result"]
        require(not replay_only, "Missing completed recalculation evidence; replay cannot execute")
        require(not (root / "started.json").exists(), "Interrupted recalculation requires explicit review")
        write_json(root / "started.json", seal({"binding_hash": binding["record_hash"]}))
        cases = (prediction.get("output") or {}).get("cases", [])
        results = []
        if public.get("answer_position") != private.get("answer_position"):
            results.append({"status": "unknown", "reason": "public_scoring_region_mismatch"})
        elif len(cases) != len(references):
            results.append({"status": "unknown", "reason": "spreadsheet_case_count_mismatch"})
        else:
            with tempfile.TemporaryDirectory(prefix="qualified-sheet-prediction-") as temporary:
                for index, (case, reference) in enumerate(zip(cases, references)):
                    if case.get("status") != "available":
                        results.append({"status": "unknown", "reason": case.get("reason", "no_workbook")})
                        continue
                    try:
                        raw = base64.b64decode(case["output_base64"], validate=True)
                        require(len(raw) <= recalc.MAX_BYTES, "Predicted workbook size limit")
                        path = Path(temporary).resolve() / f"{index}.xlsx"
                        path.write_bytes(raw)
                        result = recalc.evaluate_pair(path, reference, private["answer_position"], engine,
                                                     root / "recalculations")
                        # Detailed mismatch values stay in private execution artifacts,
                        # not in the projection available to future learning adapters.
                        results.append({key: result[key] for key in ("status", "reason", "receipts") if key in result})
                        if "container_cleanup_unconfirmed" in result["reason"]:
                            results.extend({"status": "unknown", "reason": "not_executed_after_cleanup_failure"}
                                           for _ in cases[index + 1:])
                            break
                    except (OSError, ValueError, KeyError, TypeError, zipfile.BadZipFile):
                        results.append({"status": "unknown", "reason": "recalculation_input_or_evidence_error"})
        records = [read_json(p, sealed=True) for p in sorted((root / "recalculations").glob("*.json"))]
        counts = Counter(row["status"] for row in results)
        cited = [receipt for row in results for receipt in row.get("receipts", {}).values()]
        cleanup = all(row["cleanup_confirmed"] is True for row in records)
        # An unconfirmed sandbox teardown invalidates the whole result, even if
        # another independent case already supplied a semantic failure.
        status = ("unknown" if not cleanup else "fail" if counts["fail"] else
                  "unknown" if counts["unknown"] else "pass")
        result = {"status": status, "score": None if status == "unknown" else float(status == "pass"),
            "reason": "qualified_recalculation_hard_all_cases" if cleanup else "container_cleanup_unconfirmed",
            "metrics": {"scorer_profile": VERSION, "qualification_hash": qualified["record_hash"],
                "cases": results, "case_passed": counts["pass"], "case_failed": counts["fail"],
                "case_unknown": counts["unknown"], "workbook_receipts": len(records),
                "receipt_reuses": len(cited) - len(set(cited)),
                "model_api_calls": 0, "excel_equivalence_proven": False},
            "runtime_image_id": engine.image, "cleanup_confirmed": cleanup,
            "execution_costs": {"container_calls": sum(row.get("container_execution_attempted", False) for row in records),
                "wall_seconds": sum(row.get("duration_seconds", 0) for row in records), "includes_cleanup": True,
                "image_id": engine.image}}
        artifacts = {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
                     for path in root.rglob("*.json")}
        write_json(root / "result.json", seal({"binding": binding, "result": result, "artifacts": artifacts}))
        return result
