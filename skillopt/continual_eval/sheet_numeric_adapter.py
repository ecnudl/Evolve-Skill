"""Qualified v7 numeric read-view scorer; explicit opt-in, never a v5 retry.

This profile changes the read representation of unchanged format-30 literals
and original-General numeric formula caches, never their numeric values.
Formula correctness, reference cache drift and the original content guard
remain mandatory. A new source-bound 23-control qualification is
required; old production results and their v5 authorization are not inherited.
"""
from __future__ import annotations

import base64
import hashlib
import tempfile
import zipfile
from collections import Counter
from pathlib import Path

from skillopt.coevolution_v5.core import seal

from . import sheet_recalc as recalc
from . import sheet_recalc_adapter as legacy
from . import sheet_recalc_v7 as numeric
from .core import output_lock, read_json, require, safe_path, write_json

VERSION = "qualified_lo_recalc_v7_v1"


def qualified_engine(runtime):
    """Revalidate completed qualification/receipts offline; never run Calc here."""
    from scripts import replay_sheet_v6 as qualification

    require(runtime.get("spreadsheet_scorer") == VERSION, "Explicit numeric recalculation profile required")
    spec = runtime.get("recalculation")
    require(type(spec) is dict and set(spec) == {"image", "timeout_seconds", "qualification_path",
            "qualification_sha256", "qualification_hash"}, "Invalid numeric recalculation configuration")
    require(type(spec["qualification_path"]) is str and Path(spec["qualification_path"]).is_absolute(),
            "Absolute qualification path required")
    path = safe_path(spec["qualification_path"])
    require(recalc.sha(path) == spec["qualification_sha256"], "Qualification file changed")
    qualified = read_json(path, sealed=True)
    protocol = read_json(path.parent / "protocol.json", sealed=True)
    require(protocol["kind"] == "qualification" and protocol["root"] == str(path.parent)
            and qualification._profile(protocol) == "v7", "Complete v7 qualification required")
    durable = qualification._engine(protocol, path.parent)
    engine = numeric.Recalculator(spec["image"], spec["timeout_seconds"])
    require(qualified["record_hash"] == spec["qualification_hash"]
            and qualified["version"] == qualification.VERSION and qualified["status"] == "qualified"
            and qualified["protocol_hash"] == protocol["record_hash"]
            and qualification._profile(qualified) == "v7"
            and qualified["engine"] == durable.identity == engine.identity
            and qualified["model_api_calls"] == 0 and qualified["evidence_kind"] == "engineering_fixture",
            "Qualification authorization/source/image differs")
    roster = qualification._controls("v7")
    controls = {c["name"]: c for c in protocol["controls"]}
    rows = qualified["controls"]
    require(len(rows) == len(controls) == len(protocol["controls"]) == len(roster)
            and set(controls) == {c["name"] for c in rows} == roster
            and not durable.unsafe_cleanup() and not qualification._execution(durable)["open_workbook_intents"],
            "Qualification controls or execution closure incomplete")
    qualification._published(path.parent, protocol)
    receipts = {r["record_hash"]: r for r in durable.receipts()}
    for row in rows:
        receipt = receipts[row["receipt_hash"]]
        control = controls[row["name"]]
        require(row["qualified"] is True and row["cleanup_confirmed"] is True
                and receipt["input_sha256"] == recalc.sha(control["path"])
                and receipt["identity"] == engine.identity and receipt["model_api_calls"] == 0
                and read_json(path.parent / "controls" / (row["name"] + ".json"), sealed=True) == row,
                "Qualification receipt binding differs")
        with tempfile.TemporaryDirectory(prefix="sheet-numeric-qualification-replay-") as temporary:
            verified = seal({"protocol_hash": protocol["record_hash"],
                **qualification._control_result(control, receipt, Path(temporary).resolve())})
        require(verified == row, "Qualification judgment changed")
    return engine, qualified


def readiness(runtime):
    from .backends import _image_ready

    try:
        engine, _ = qualified_engine(runtime)
    except (OSError, ValueError, KeyError, TypeError):
        return {"status": "unsupported", "reason": "invalid_numeric_recalculation_qualification"}
    return _image_ready({"image": engine.image})


def score(public, private, prediction, *, runtime, replay_only=False):
    engine, qualified = qualified_engine(runtime)
    root, old_binding = legacy._context(runtime, public, private, prediction, qualified)
    binding = seal({**{k: v for k, v in old_binding.items() if k != "record_hash"}, "version": VERSION})
    references = private["test_files"]
    require(type(references) is list and references, "Reference cases required")
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
        require(not replay_only, "Missing completed numeric evidence; replay cannot execute")
        require(not (root / "started.json").exists(), "Interrupted recalculation requires explicit review")
        write_json(root / "started.json", seal({"binding_hash": binding["record_hash"]}))
        cases = (prediction.get("output") or {}).get("cases", [])
        results = []
        if public.get("answer_position") != private.get("answer_position"):
            results.append({"status": "unknown", "reason": "public_scoring_region_mismatch"})
        elif len(cases) != len(references):
            results.append({"status": "unknown", "reason": "spreadsheet_case_count_mismatch"})
        else:
            with tempfile.TemporaryDirectory(prefix="numeric-sheet-prediction-") as temporary:
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
        status = "unknown" if not cleanup else "fail" if counts["fail"] else "unknown" if counts["unknown"] else "pass"
        result = {"status": status, "score": None if status == "unknown" else float(status == "pass"),
            "reason": "qualified_numeric_recalculation_hard_all_cases" if cleanup else "container_cleanup_unconfirmed",
            "metrics": {"scorer_profile": VERSION, "qualification_hash": qualified["record_hash"],
                "cases": results, "case_passed": counts["pass"], "case_failed": counts["fail"],
                "case_unknown": counts["unknown"], "workbook_receipts": len(records),
                "receipt_reuses": len(cited) - len(set(cited)), "model_api_calls": 0,
                "excel_equivalence_proven": False}, "runtime_image_id": engine.image,
            "cleanup_confirmed": cleanup,
            "execution_costs": {"container_calls": sum(row.get("container_execution_attempted", False) for row in records),
                "wall_seconds": sum(row.get("duration_seconds", 0) for row in records), "includes_cleanup": True,
                "image_id": engine.image}}
        artifacts = {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
                     for path in root.rglob("*.json")}
        write_json(root / "result.json", seal({"binding": binding, "result": result, "artifacts": artifacts}))
        return result
