"""One zero-API sidecar: saved 56786/r1 fenced workbook versus frozen C H.

Run under C's original source/interpreter. The fenced report is independently
verified under its own original source/interpreter. Neither historical run is
changed; this is delivery repair plus a new scoring protocol, not Skill effect.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import subprocess
from pathlib import Path

from scripts import replay_sheet_frozen_gold as frozen
from scripts import replay_sheet_v6 as replay
from skillopt.coevolution_v5.core import seal, verify
from skillopt.continual_eval import sheet_frozen_gold as scoring
from skillopt.continual_eval import sheet_recalc as recalc
from skillopt.continual_eval.core import output_lock, read_json, require, safe_path, write_json
from skillopt.continual_eval.truncation_recovery import _readonly_parent_lock

VERSION = "single-fenced-delivery-frozen-c-h-v1"
POSITION = "b8bb5b8443a61c95936321863988ebbbe22c638792f8b13d4e5eb7971cf7c153"
CASE_HASH = "ef9159a4e8c184914dcba6a32fa1485bf87c67c1ab0c36a972fbe6a738086866"
REFERENCE_ID = "ad263a68bcd00a3ff1334606fd1d64c0e699b8047dde1a07d26537047801eec6"


def _fenced_report(root, python, script, protocol):
    """Original read-only report verifies receipts and literal-extraction audit."""
    require(recalc.sha(script) == protocol["script_sha256"], "Fenced report script changed")
    source = safe_path(protocol["source"])
    interpreter = Path(python).absolute()  # Preserve a venv executable's symlink name.
    require(interpreter.is_file() and ".." not in interpreter.parts, "Explicit original interpreter required")
    process = subprocess.run(
        [str(interpreter), str(safe_path(script)), "report", "--output", str(root)],
        cwd=source, env={**os.environ, "PYTHONPATH": str(source), "PYTHONDONTWRITEBYTECODE": "1"},
        capture_output=True, text=True, timeout=600, check=False)
    require(process.returncode == 0, "Original fenced report verification failed")
    result = verify(json.loads(process.stdout))
    require(read_json(root / "reports" / (result["record_hash"] + ".json"), sealed=True) == result,
            "Fenced report is not already published; historical writes are forbidden")
    return result


def _bind(c_protocol, c_report, c_row, f_protocol, f_report, record, case, manifest):
    """Exact saved case -> original position -> C reference; no model text."""
    slots = [slot for slot in c_protocol["slots"] if slot["id"] == POSITION]
    require(len(slots) == 1, "Exactly one authorized C position required")
    slot = slots[0]
    require(slot["task_id"] == "56786" and slot["repeat"] == 1
            and slot["reference_manifests"] == [REFERENCE_ID] and len(slot["references"]) == 1,
            "Only the declared one-case 56786/r1 sidecar is authorized")
    require(c_report["status"] == "complete" and c_report["completed"] == c_report["positions"] == 160
            and c_report["protocol_hash"] == c_protocol["record_hash"]
            and c_report["result_hashes"][POSITION] == c_row["record_hash"]
            and c_row["protocol_hash"] == c_protocol["record_hash"] and c_row["slot_id"] == POSITION,
            "C published position binding changed")
    require(f_protocol["version"] == "frozen-fenced-delivery-replay-v1"
            and f_protocol["parent"] == c_protocol["original_source"]
            and f_report["status"] == "completed" and f_report["cleanup_unconfirmed"] is False
            and f_report["new_model_calls"] == 0 and f_report["protocol_hash"] == f_protocol["record_hash"]
            and f_report["record_hashes"][POSITION] == record["record_hash"], "Fenced report binding changed")
    item = record["identity"]["item"]
    require(record["identity"]["protocol_hash"] == f_protocol["record_hash"]
            and item in f_protocol["audit"] and item["position"] == POSITION and item["repeat"] == 1
            and item["prediction_hash"] == slot["prediction_hash"] and item["score_hash"] == slot["old_score_hash"]
            and item["eligible"] is True and item["closed_stop"] is True
            and record["cleanup_unconfirmed"] is False and record["new_model_calls"] == 0
            and record["case_record_hashes"] == [case["record_hash"]] == [CASE_HASH]
            and record["cases"] == [{k: v for k, v in case.items() if k not in {"record_hash", "output_base64"}}],
            "Fenced case/original position identity changed")
    require(case["status"] == "available" and case["cleanup_confirmed"] is True
            and manifest["status"] == "available" and manifest["provenance"]["task_id"] == "56786"
            and manifest["answer_position"] == slot["answer_position"], "Delivered case or frozen H unavailable")
    raw = base64.b64decode(case["output_base64"], validate=True)
    require(0 < len(raw) <= recalc.MAX_BYTES, "Candidate workbook size limit")
    return slot, raw


def run(*, fenced_root, fenced_script, fenced_python, c_root, engine_qualification, output, native_lock):
    fenced_root, c_root, qpath, root = map(safe_path, (fenced_root, c_root, engine_qualification, output))
    require(all(not root.is_relative_to(old) and not old.is_relative_to(root)
                for old in (fenced_root, c_root, qpath.parent)), "Separate new sidecar directory required")
    lock = replay._lock_path(native_lock, (root, fenced_root, c_root, qpath.parent))
    with _readonly_parent_lock(fenced_root), _readonly_parent_lock(c_root):
        cp, fp = read_json(c_root / "protocol.json", sealed=True), read_json(fenced_root / "protocol.json", sealed=True)
        require(cp["version"] == frozen.VERSION and cp["root"] == str(c_root)
                and fp["output"] == str(fenced_root), "Historical root identity changed")
        require(all(not root.is_relative_to(old) and not old.is_relative_to(root)
                    for old in (safe_path(fp["source"]), safe_path(fp["parent"]), Path(scoring.__file__).parents[2])),
                "Sidecar output must not be inside historical sources or original evidence")
        cr = frozen.report(c_root)  # This function returns a report without publishing it.
        require(read_json(c_root / "reports" / (cr["record_hash"] + ".json"), sealed=True) == cr,
                "C report is not already published")
        fr = _fenced_report(fenced_root, fenced_python, fenced_script, fp)
        c_row = read_json(c_root / "positions" / (POSITION + ".json"), sealed=True)
        record = read_json(fenced_root / "records" / (POSITION + ".json"), sealed=True)
        require(read_json(fenced_root / "intents" / (POSITION + ".json"), sealed=True) == seal(record["identity"]),
                "Fenced execution intent changed")
        case = read_json(fenced_root / "cases" / POSITION / "0.json", sealed=True)
        h_path = c_root / "host_only/references" / (REFERENCE_ID + ".json")
        h = read_json(h_path, sealed=True)
        slot, raw = _bind(cp, cr, c_row, fp, fr, record, case, h)
        q, base_engine, _ = frozen._engine_qualification(qpath)
        require(q["record_hash"] == cp["engine_qualification_hash"] and base_engine.identity == cp["engine"],
                "Use the existing C-qualified engine, not a new or inherited engine")
        require(recalc.sha(slot["references"][0]) == h["reference_sha256"], "Frozen H source bytes changed")
        protocol = seal({"version": VERSION, "root": str(root), "position": POSITION, "task_id": "56786", "repeat": 1,
            "c_protocol_hash": cp["record_hash"], "c_report_hash": cr["record_hash"], "c_position_hash": c_row["record_hash"],
            "slot": slot, "fenced_protocol_hash": fp["record_hash"], "fenced_report_hash": fr["record_hash"],
            "fenced_record_hash": record["record_hash"], "fenced_case_hash": case["record_hash"],
            "reference_manifest_hash": h["record_hash"], "candidate_sha256": hashlib.sha256(raw).hexdigest(),
            "engine": base_engine.identity, "engine_qualification_hash": q["record_hash"],
            "score_qualification_hash": cp["score_qualification_hash"], "native_lock": str(lock),
            "sources": {**frozen._sources(), str(Path(__file__).resolve()): recalc.sha(__file__)},
            "new_model_calls": 0, "reference_engine_calls": 0, "historical_scores_replaced": False,
            "feedback_allowed": False, "is_method_effect": False})
        require(not root.exists() or (root / "protocol.json").is_file(), "Unidentified existing sidecar output")
        with output_lock(root):
            write_json(root / "protocol.json", protocol)
            engine = replay.DurableEngine(base_engine, root, lock)
            require(not engine.unsafe_cleanup() and not replay._execution(engine)["open_workbook_intents"],
                    "Unclosed or unsafe sidecar; do not reexecute")
            candidate = root / "candidate.xlsx"
            if candidate.exists():
                require(recalc.sha(candidate) == protocol["candidate_sha256"], "Saved candidate bytes changed")
            else:
                candidate.write_bytes(raw)
            target = root / "result.json"
            if target.exists():
                result = read_json(target, sealed=True)
                receipts = {r["record_hash"]: r for r in engine.receipts()}
                require(result["protocol_hash"] == protocol["record_hash"]
                        and result["execution"] == replay._execution(engine)
                        and result["candidate_sha256"] == protocol["candidate_sha256"]
                        and result["score"]["reference_manifest_hash"] == h["record_hash"]
                        and set(result["score"]["receipts"]) == {"prediction"}
                        and all(token in receipts and receipts[token]["input_sha256"] == protocol["candidate_sha256"]
                                for token in result["score"]["receipts"].values()), "Published sidecar evidence changed")
                require(scoring.evaluate(candidate, slot["references"][0], slot["answer_position"], engine, h)
                        == result["score"], "Published sidecar score differs from saved candidate receipt")
                return result
            score = scoring.evaluate(candidate, slot["references"][0], slot["answer_position"], engine, h)
            result = seal({"version": VERSION, "protocol_hash": protocol["record_hash"], "positions": 1,
                "status": "pending" if engine.unsafe_cleanup() else "complete", "score": score,
                "execution": replay._execution(engine), "candidate_sha256": protocol["candidate_sha256"],
                "original_c_status": c_row["status"], "original_fenced_status": record["score"]["status"],
                "truth_basis": cp["truth_basis"], "new_model_calls": 0, "reference_engine_calls": 0,
                "historical_scores_replaced": False, "feedback_allowed": False, "is_method_effect": False})
            write_json(target, result)
            return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("fenced-root", "fenced-script", "fenced-python", "c-root", "engine-qualification", "output", "native-lock"):
        parser.add_argument("--" + name, required=True)
    print(json.dumps(run(**vars(parser.parse_args())), ensure_ascii=False))


if __name__ == "__main__":
    main()
