"""Opt-in zero-API replay: frozen dataset-cache H, candidate-only recalculation.

This does not replace historical scores or establish fresh Excel ground truth.
Requires independent engine and scoring controls in this exact source tree.
"""
from __future__ import annotations

import argparse
import base64
import json
import tempfile
from collections import Counter
from pathlib import Path

from scripts import replay_sheet_v6 as replay
from skillopt.coevolution_v5.core import seal
from skillopt.continual_eval import sheet_frozen_gold as scoring
from skillopt.continual_eval import sheet_recalc as recalc
from skillopt.continual_eval.core import output_lock, read_json, require, safe_path, write_json
from skillopt.continual_eval.truncation_recovery import _readonly_parent_lock
from skillopt.validator_pilot.api import digest

VERSION = "spreadsheet-frozen-gold-full-replay-v1"


def _sources():
    return replay._files([__file__, scoring.__file__, replay.__file__])


def _engine_qualification(path):
    path = safe_path(path)
    q, protocol = read_json(path, sealed=True), read_json(path.parent / "protocol.json", sealed=True)
    require(replay._profile(protocol) == "v8", "Native qualified-function engine required")
    engine = replay._engine(protocol, path.parent)
    replay._validate_function_controls(protocol)
    replay._published(path.parent, protocol)
    roster = replay._controls("v8")
    require(protocol["kind"] == "qualification" and protocol["root"] == str(path.parent)
            and q["version"] == replay.VERSION and q["status"] == "qualified"
            and q["engine"] == engine.identity and replay._profile(q) == "v8"
            and q["protocol_hash"] == protocol["record_hash"] and q["model_api_calls"] == 0
            and len(q["controls"]) == len(roster) and {c["name"] for c in q["controls"]} == roster
            and all(c["qualified"] for c in q["controls"])
            and q["execution"] == replay._execution(engine)
            and not engine.unsafe_cleanup() and replay._execution(engine)["open_workbook_intents"] == 0,
            "Complete independent engine qualification required")
    specs = {c["name"]: c for c in protocol["controls"]}
    require(len(specs) == len(protocol["controls"]) == len(roster) and set(specs) == roster,
            "Engine fixture roster changed")
    receipts = {r["record_hash"]: r for r in engine.receipts()}
    for row in q["controls"]:
        receipt = receipts.get(row["receipt_hash"])
        require(receipt and receipt["input_sha256"] == recalc.sha(specs[row["name"]]["path"])
                and row["cleanup_confirmed"] is True
                and read_json(path.parent / "controls" / (row["name"] + ".json"), sealed=True) == row,
                "Engine control evidence changed")
        with tempfile.TemporaryDirectory(prefix="frozen-gold-engine-control-") as temp:
            actual = seal({"protocol_hash": protocol["record_hash"],
                **replay._control_result(specs[row["name"]], receipt, Path(temp).resolve())})
        require(actual == row, "Engine control judgment changed")
    inventory = replay._files(list(path.parent.rglob("*.json")))
    inventory.update(protocol["inventory"])
    return q, engine.engine, inventory


def _engine(protocol, root):
    require(protocol["version"] == VERSION and protocol["sources"] == _sources(), "Scoring source changed")
    replay._verify_files(protocol["inventory"])
    engine = replay.v8.Recalculator(protocol["engine"]["image_id"], protocol["engine"]["timeout_seconds"])
    require(engine.identity == protocol["engine"], "Native engine identity changed")
    return replay.DurableEngine(engine, root, protocol["native_lock"])


def qualify_score(output, qualification=None, native_lock=None):
    root = safe_path(output)
    if not root.exists():
        require(qualification and native_lock, "New scoring qualification arguments required")
        qpath = safe_path(qualification)
        require(not root.is_relative_to(qpath.parent) and not qpath.parent.is_relative_to(root),
                "Separate scoring qualification directory required")
        q, engine, inventory = _engine_qualification(qpath)
        lock = replay._lock_path(native_lock, (root, qpath.parent))
        root.mkdir(parents=True, mode=0o700)
        write_json(root / "protocol.json", seal({"version": VERSION, "kind": "score_qualification",
            "root": str(root), "sources": _sources(), "inventory": inventory, "engine": engine.identity,
            "engine_qualification_hash": q["record_hash"], "native_lock": str(lock)}))
    with output_lock(root):
        protocol = read_json(root / "protocol.json", sealed=True)
        require(protocol["kind"] == "score_qualification" and protocol["root"] == str(root), "Wrong score qualification root")
        engine = _engine(protocol, root)
        require(not engine.unsafe_cleanup() and not replay._execution(engine)["open_workbook_intents"],
                "Unclosed or unsafe scoring execution")
        judged = scoring.qualify(root / "fixtures", engine)
        names = {c["name"] for c in judged["controls"]}
        require(names <= scoring.SCORE_CONTROLS and len(names) == len(judged["controls"]),
                "Scoring control roster changed")
        execution = replay._execution(engine)
        status = ("pending" if names != scoring.SCORE_CONTROLS or execution["open_workbook_intents"] or execution["cleanup_unconfirmed"]
                  else judged["status"])
        result = seal({"version": VERSION, "status": status, "protocol_hash": protocol["record_hash"],
            "engine": engine.identity, "sources": _sources(), "score_qualification": judged,
            "execution": execution, "evidence_kind": "engineering_fixture", "model_api_calls": 0})
        write_json(root / "reports" / (result["record_hash"] + ".json"), result)
        if status != "pending":
            write_json(root / "qualification.json", result)
        return result


def _score_qualification(path, engine):
    path = safe_path(path)
    saved = read_json(path, sealed=True)
    require(saved["status"] == "qualified" and saved["engine"] == engine.identity
            and saved["sources"] == _sources() and saved["model_api_calls"] == 0,
            "Independent scoring qualification required")
    require(qualify_score(path.parent) == saved, "Frozen scoring judgments changed")
    protocol = read_json(path.parent / "protocol.json", sealed=True)
    inventory = replay._files(list(path.parent.rglob("*.json")) + list((path.parent / "fixtures").rglob("*.xlsx")))
    inventory.update(protocol["inventory"])
    return saved, inventory


def _previous(root):
    """Verify historical identities as recorded, not against new source paths."""
    root = safe_path(root)
    protocol = read_json(root / "protocol.json", sealed=True)
    require(protocol["version"] == replay.VERSION and protocol["kind"] == "replay"
            and protocol["root"] == str(root) and replay._profile(protocol) == "v8"
            and protocol["engine"]["version"] == replay.v8.VERSION
            and protocol["script_sha256"] == recalc.sha(replay.__file__), "Expected frozen v8b replay required")
    replay._verify_files(protocol["inventory"])
    replay._verify_files(protocol["engine"]["sources"])
    replay._published(root, protocol)
    slots = protocol["slots"]
    require(len(slots) == len({s["id"] for s in slots}) == 160
            and len({s["task_id"] for s in slots}) == 80
            and all({s["repeat"] for s in slots if s["task_id"] == task} == {0, 1}
                    for task in {s["task_id"] for s in slots})
            and {p.stem for p in (root / "positions").glob("*.json")} == {s["id"] for s in slots},
            "Complete original 80-task / 160-position roster required")
    # This proxy validates prior receipt identity only; it has no execution method.
    class FrozenIdentity:
        identity = protocol["engine"]
    prior_engine = replay.DurableEngine(FrozenIdentity(), root, protocol["native_lock"])
    costs = replay._execution(prior_engine)
    require(not costs["open_workbook_intents"] and not costs["cleanup_unconfirmed"], "Previous replay unfinished or unsafe")
    receipts = {r["record_hash"]: r for r in prior_engine.receipts()}
    rows = {}
    for slot in slots:
        row = read_json(root / "positions" / (slot["id"] + ".json"), sealed=True)
        require(row["protocol_hash"] == protocol["record_hash"] and row["slot_id"] == slot["id"]
                and row["old_status"] == slot["old_status"] and row["model_api_calls"] == 0,
                "Previous result identity changed")
        prediction = read_json(slot["prediction_path"], sealed=True)
        require(prediction["record_hash"] == slot["prediction_hash"], "Original prediction changed")
        for case in row["cases"]:
            require(all(h in receipts for h in case.get("receipts", {}).values()), "Previous case receipt missing")
        rows[slot["id"]] = row
    require(Counter(s["old_status"] for s in slots) == {"pass": 63, "fail": 44, "unknown": 53}
            and Counter(r["status"] for r in rows.values()) == {"pass": 70, "fail": 48, "unknown": 42},
            "Historical panel counts differ from frozen v8b source")
    return protocol, rows


def prepare(previous_replay, qualification, score_qualification, output, native_lock):
    previous, qpath, spath, root = map(safe_path, (previous_replay, qualification, score_qualification, output))
    require(not root.exists() and all(not root.is_relative_to(p) and not p.is_relative_to(root)
            for p in (previous, qpath.parent, spath.parent)), "Separate new replay directory required")
    lock = replay._lock_path(native_lock, (previous, qpath.parent, spath.parent, root))
    q, engine, inventory = _engine_qualification(qpath)
    sq, score_files = _score_qualification(spath, engine)
    inventory.update(score_files)
    with _readonly_parent_lock(previous):
        prior, rows = _previous(previous)
        with _readonly_parent_lock(Path(prior["source"])):
            inventory.update(prior["inventory"])
            inventory.update(replay._files(list(previous.rglob("*.json"))))
            inventory.update(prior["engine"]["sources"])
            slots, manifests, disputed = [], {}, set()
            for slot in prior["slots"]:
                for index, case in enumerate(rows[slot["id"]]["cases"]):
                    if case.get("reason") == "reference_native_cache_drift_or_unavailable":
                        require(index < len(slot["references"]), "Reference disagreement index missing")
                        disputed.add(slot["references"][index])
            for slot in prior["slots"]:
                ids = []
                for reference in slot["references"]:
                    expected = prior["inventory"].get(reference)
                    require(expected and recalc.sha(reference) == expected, "Original reference inventory changed")
                    key = digest({"reference": reference, "sha256": expected, "target": slot["answer_position"]})
                    manifest = scoring.freeze_reference(reference, expected, slot["answer_position"],
                        provenance={"source_protocol_hash": prior["record_hash"], "task_id": slot["task_id"],
                                    "evidence_kind": "frozen_real_model_replay", "partition": "development"},
                        dispute=reference in disputed)
                    require(key not in manifests or manifests[key] == manifest, "Reference provenance conflict")
                    manifests[key] = manifest
                    ids.append(key)
                slots.append({**slot, "previous_status": rows[slot["id"]]["status"],
                              "previous_result_hash": rows[slot["id"]]["record_hash"], "reference_manifests": ids})
            root.mkdir(parents=True, mode=0o700)
            for key, manifest in manifests.items():
                path = root / "host_only" / "references" / (key + ".json")
                write_json(path, manifest)
                inventory.update(replay._files([path]))
            protocol = seal({"version": VERSION, "kind": "replay", "root": str(root), "sources": _sources(),
                "previous_replay": str(previous), "original_source": prior["source"],
                "previous_protocol_hash": prior["record_hash"], "engine": engine.identity,
                "engine_qualification_hash": q["record_hash"], "score_qualification_hash": sq["record_hash"],
                "native_lock": str(lock), "inventory": inventory, "slots": slots,
                "disputed_reference_count": len(disputed), "model_api_calls": 0,
                "historical_scores_replaced": False, "feedback_allowed": False,
                "truth_basis": "frozen_benchmark_label_not_independent_oracle"})
            write_json(root / "protocol.json", protocol)
    return {"status": "prepared", "positions": len(slots), "reference_manifests": len(manifests),
            "disputed_references": len(disputed), "protocol_hash": protocol["record_hash"]}


def _published(root, protocol):
    for path in (root / "reports").glob("*.json"):
        saved = read_json(path, sealed=True)
        require(saved["protocol_hash"] == protocol["record_hash"], "Published protocol differs")
        for key, expected in saved["result_hashes"].items():
            require(read_json(root / "positions" / (key + ".json"), sealed=True)["record_hash"] == expected,
                    "Published result changed")


def report(output):
    root = safe_path(output)
    protocol = read_json(root / "protocol.json", sealed=True)
    require(protocol["kind"] == "replay" and protocol["root"] == str(root), "Wrong replay root")
    engine = _engine(protocol, root)
    _published(root, protocol)
    rows = []
    for slot in protocol["slots"]:
        path = root / "positions" / (slot["id"] + ".json")
        if path.exists():
            row = read_json(path, sealed=True)
            require(row["protocol_hash"] == protocol["record_hash"] and row["slot_id"] == slot["id"]
                    and row["old_status"] == slot["old_status"] and row["previous_status"] == slot["previous_status"],
                    "Position identity changed")
            rows.append(row)
    execution = replay._execution(engine)
    counts = Counter(r["status"] for r in rows)
    return seal({"version": VERSION, "protocol_hash": protocol["record_hash"],
        "status": "complete" if len(rows) == len(protocol["slots"]) and not execution["open_workbook_intents"]
                  and not execution["cleanup_unconfirmed"] else "pending",
        "positions": len(protocol["slots"]), "completed": len(rows), "counts": dict(counts),
        "original_counts": dict(Counter(s["old_status"] for s in protocol["slots"])),
        "previous_counts": dict(Counter(s["previous_status"] for s in protocol["slots"])),
        "original_transitions": dict(Counter(r["old_status"] + "->" + r["status"] for r in rows)),
        "previous_transitions": dict(Counter(r["previous_status"] + "->" + r["status"] for r in rows)),
        "delivery_evaluation_axes": dict(Counter(r["delivery_status"] + "->" + r["status"] for r in rows)),
        "unknown_reasons": dict(Counter(c["reason"] for r in rows for c in r["cases"] if c["status"] == "unknown")),
        "known_correctness": {"passes": counts["pass"], "known_positions": counts["pass"] + counts["fail"]},
        "result_hashes": {r["slot_id"]: r["record_hash"] for r in rows}, "execution": execution,
        "model_api_calls": 0, "reference_engine_calls": 0, "historical_scores_replaced": False,
        "feedback_allowed": False, "is_method_effect": False, "excel_equivalence_proven": False,
        "truth_basis": protocol["truth_basis"]})


def run(output):
    root = safe_path(output)
    with output_lock(root):
        protocol = read_json(root / "protocol.json", sealed=True)
        engine = _engine(protocol, root)
        require(protocol["kind"] == "replay" and protocol["root"] == str(root), "Wrong replay root")
        require(not engine.unsafe_cleanup() and not replay._execution(engine)["open_workbook_intents"],
                "Unclosed or unsafe workbook execution")
        report(root)
        with _readonly_parent_lock(Path(protocol["previous_replay"])), _readonly_parent_lock(Path(protocol["original_source"])):
            for slot in protocol["slots"]:
                require(slot["references"] and len(slot["reference_manifests"]) == len(slot["references"]),
                        "Reference manifest roster changed")
                path = root / "positions" / (slot["id"] + ".json")
                if path.exists():
                    continue
                if (root / "PAUSE").exists():
                    break
                saved = read_json(slot["prediction_path"], sealed=True)
                require(saved["record_hash"] == slot["prediction_hash"], "Original prediction changed")
                prediction = saved["prediction"]
                cases = (prediction.get("output") or {}).get("cases", [])
                results, delivery = [], "undelivered"
                if prediction["status"] != "available" or not cases:
                    results = [recalc._undelivered(prediction["reason"])]
                elif len(cases) != len(slot["references"]):
                    results = [{"status": "unknown", "reason": "original_case_count_mismatch"}]
                    delivery = "case_count_mismatch"
                else:
                    delivered = sum(case["status"] == "available" for case in cases)
                    delivery = "delivered" if delivered == len(cases) else "partial" if delivered else "undelivered"
                    with tempfile.TemporaryDirectory(prefix="frozen-gold-prediction-") as temp:
                        for index, (case, reference, manifest_id) in enumerate(zip(cases, slot["references"], slot["reference_manifests"])):
                            if case["status"] != "available":
                                results.append(recalc._undelivered(case["reason"]))
                                continue
                            raw = base64.b64decode(case["output_base64"], validate=True)
                            require(len(raw) <= recalc.MAX_BYTES, "Candidate workbook size limit")
                            candidate = Path(temp).resolve() / f"{index}.xlsx"
                            candidate.write_bytes(raw)
                            manifest = read_json(root / "host_only" / "references" / (manifest_id + ".json"), sealed=True)
                            results.append(scoring.evaluate(candidate, reference, slot["answer_position"], engine, manifest))
                            if engine.unsafe_cleanup():
                                break
                counts = Counter(c["status"] for c in results)
                status = "unknown" if engine.unsafe_cleanup() else "fail" if counts["fail"] else "unknown" if counts["unknown"] else "pass"
                write_json(path, seal({"protocol_hash": protocol["record_hash"], "slot_id": slot["id"],
                    "old_status": slot["old_status"], "previous_status": slot["previous_status"],
                    "status": status, "delivery_status": delivery, "cases": results, "model_api_calls": 0}))
                if engine.unsafe_cleanup():
                    break
        result = report(root)
        write_json(root / "reports" / (result["record_hash"] + ".json"), result)
        return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("qualify-score", "prepare", "run", "report"))
    parser.add_argument("--output", required=True)
    parser.add_argument("--engine-qualification")
    parser.add_argument("--score-qualification")
    parser.add_argument("--previous-replay")
    parser.add_argument("--native-lock")
    args = parser.parse_args(argv)
    if args.command == "qualify-score":
        result = qualify_score(args.output, args.engine_qualification, args.native_lock)
    elif args.command == "prepare":
        require(all((args.previous_replay, args.engine_qualification, args.score_qualification, args.native_lock)),
                "Preparation arguments required")
        result = prepare(args.previous_replay, args.engine_qualification, args.score_qualification, args.output, args.native_lock)
    else:
        result = {"run": run, "report": report}[args.command](args.output)
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
