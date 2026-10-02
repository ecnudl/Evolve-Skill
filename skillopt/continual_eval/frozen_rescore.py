"""Zero-model, all-800 BCB re-scoring after a separately qualified data overlay.

Original predictions and scores remain immutable. This is an environment
comparison, never a Skill gate or a new generation/learning experiment.
"""
from __future__ import annotations

import argparse
import re
from collections import Counter
from copy import deepcopy

from skillopt.coevolution_v5.core import seal
from skillopt.validator_pilot.api import digest

from . import backends
from . import reference_qualification as reference
from .core import load_checkpoint, output_lock, read_json, require, safe_path, source_identity, write_json
from .runner import _costs, _stored_calls, position

VERSION = "bcb-full-frozen-prediction-rescore-v2"


def _detail_text(value):
    if type(value) is str:
        return re.sub(r"\x1b\[[0-9;]*m", "", value)
    if type(value) is dict:
        value = list(value.values())
    return "\n".join(_detail_text(v) for v in value) if type(value) is list else ""


def _validate_original(receipt, score, plan, *, fixture):
    require(type(receipt.get("ok")) is bool, "Original API outcome is invalid")
    if not fixture:
        require(type(receipt.get("http_attempt_count")) is int and receipt["http_attempt_count"] >= 1
                and (not receipt["ok"] or receipt.get("returned_model") == plan["config"]["model"]["name"]),
                "Original actual response identity/attempts differ")
    native = {k: score[k] for k in ("status", "score", "reason", "metrics", "runtime_image_id",
                                  "cleanup_confirmed", "runtime_architecture", "execution_costs") if k in score}
    reference._validated_score(native, {"fixture": fixture, "runtime": plan["config"]["runtime"]["bigcodebench"]})


def _reference(root):
    """Replay the old verifier with exact old sources plus this one new module."""
    protocol = read_json(root / "protocol.json", sealed=True)
    current = source_identity()
    require(all(current.get(k) == v for k, v in protocol["source_identity"].items())
            and set(current) - set(protocol["source_identity"]) <= {"continual_eval/frozen_rescore.py"},
            "Qualification execution source changed")
    data = reference._inputs(safe_path(protocol["plan_path"]), safe_path(protocol["raw_root"]))
    expected = reference._protocol(safe_path(protocol["plan_path"]), safe_path(protocol["raw_root"]),
                                   safe_path(protocol["native_lock"]), data)
    expected.pop("record_hash")
    expected["source_identity"] = protocol["source_identity"]
    require(protocol == seal(expected), "Qualification protocol differs")
    result = read_json(root / "result.json", sealed=True)
    require(result == reference._report(root, protocol, data) and result["status"] == "completed"
            and result["cleanup_confirmed"] == 400, "Full clean reference qualification required")
    _, rows = reference._records(root, protocol, data)
    return protocol, data, result, {r["request"]["task_hash"]: r for r in rows.values()}


def _qualified(root):
    protocol, data, result, rows = _reference(root)
    meta = data["plan"]["environment_qualification"]
    oldroot = safe_path(meta["original_reference_report_path"]).parent
    oldprotocol, olddata, oldresult, oldrows = _reference(oldroot)
    require(oldresult["record_hash"] == meta["original_reference_report_hash"]
            and reference._sha(oldroot / "result.json") == meta["original_reference_report_file_sha256"]
            and protocol["source_identity"] == oldprotocol["source_identity"]
            and data["references"] == olddata["references"] and data["fixture"] == olddata["fixture"],
            "Original reference comparison changed")
    for key, path_key, hash_key in (("overlay_manifest", "overlay_manifest_path", "overlay_manifest_file_sha256"),
                                  ("overlay_build_receipt", "overlay_receipt_path", "overlay_receipt_file_sha256")):
        path = safe_path(meta[path_key])
        require(read_json(path, sealed=True) == meta[key] and reference._sha(path) == meta[hash_key],
                "Overlay source evidence changed")
    manifest, receipt = meta["overlay_manifest"], meta["overlay_build_receipt"]
    require(receipt["status"] == "built_not_qualified" and receipt["manifest_hash"] == manifest["record_hash"]
            and receipt["base_image"] == olddata["runtime"]["image"]
            and receipt["image_id"] == data["runtime"]["image"] and receipt["base_configuration_preserved"] is True
            and manifest["version"] == "bcb-nltk-data-overlay-v2" and manifest["base_image"] == receipt["base_image"],
            "Wrong data-only image provenance")
    require({k: v for k, v in data["runtime"].items() if k != "image"}
            == {k: v for k, v in olddata["runtime"].items() if k != "image"}, "Runtime budget changed")
    targets = set(meta["acceptance_frozen_before_execution"]["target_task_hashes"])
    original_pass = {h for h, row in oldrows.items() if row["score"]["status"] == "pass"}
    missing = set()
    for h, row in oldrows.items():
        text = _detail_text(row["score"]["metrics"].get("details", {}))
        if re.search(r"Resource\s+(?:punkt|stopwords)\s+not found", text):
            missing.add(h)
    require(len(original_pass) == 393 and len(targets) == 5 and targets == missing
            and all(oldrows[h]["score"]["status"] == "fail" for h in targets), "Predeclared qualification scope differs")
    require(all(rows[h]["score"]["status"] == "pass" for h in original_pass | targets),
            "Data-only qualification has regression or unrepaired target")
    parent = safe_path(meta["parent_plan_path"]).parent
    require(read_json(parent / "plan.json", sealed=True) == olddata["plan"]
            and olddata["plan"]["record_hash"] == meta["parent_plan_hash"]
            and reference._sha(parent / "plan.json") == meta["parent_plan_file_sha256"], "Wrong original model plan")
    expected = deepcopy(olddata["plan"])
    expected.pop("record_hash")
    expected["config"]["runtime"]["bigcodebench"]["image"] = data["runtime"]["image"]
    expected.update(checkpoints=[], environment_qualification=meta)
    require(data["plan"] == seal(expected), "Metadata-only plan has additional changes")
    return protocol, data, parent, {"new_reference_report_hash": result["record_hash"],
        "old_reference_report_hash": oldresult["record_hash"], "retained_reference_passes": 393,
        "repaired_resource_targets": 5, "other_reference_statuses": dict(Counter(
            rows[h]["score"]["status"] for h in set(rows) - original_pass - targets)),
        "overlay_manifest_hash": manifest["record_hash"], "overlay_receipt_hash": receipt["record_hash"]}


def _snapshot(qualification):
    qprotocol, data, parent, authorization = _qualified(qualification)
    plan = read_json(parent / "plan.json", sealed=True)
    require(plan["repeats"] == 2 and len(plan["tasks"]) == 400
            and plan["config"]["methods"] == ["no_skill"], "Use all original 400 tasks by two repeats")
    cp = load_checkpoint(parent, "no_skill", "h0", 0, plan)
    service = read_json(parent / "model_service.json", sealed=True)
    service.pop("record_hash")
    slots, calls = [], []
    for ref in data["references"]:
        task = ref["task"]
        for repeat in range(2):
            base, request = position(parent, cp, "bigcodebench", task, repeat)
            prediction = read_json(base / "prediction.json", sealed=True)
            score = read_json(parent / "host_only/scores" / (base.name + ".json"), sealed=True)
            receipts = _stored_calls(base)
            require(len(receipts) == len(list((base / "call_intents").glob("*.json"))) == 1
                    and prediction["request"] == request and prediction["costs"] == _costs(receipts)
                    and score["prediction_hash"] == prediction["record_hash"]
                    and score["plan_hash"] == plan["record_hash"] and score["checkpoint_hash"] == cp["record_hash"]
                    and score["task_id"] == task["task_id"] and score["family_id"] == task["family_id"]
                    and score["repeat"] == repeat and score["costs"] == _costs(receipts),
                    "Original model evidence is incomplete/mismatched")
            require(read_json(base / "intent.json", sealed=True) == seal(request)
                    and read_json(parent / "host_only/score_intents" / (base.name + ".json"), sealed=True)
                    == seal({"request": request, "prediction_hash": prediction["record_hash"]})
                    and read_json(next((base / "calls").glob("*.json")), sealed=True)["request"]["position"] == request
                    and receipts[0]["request"]["service"] == service
                    and receipts[0]["request"]["model"] == plan["config"]["model"]["name"]
                    and receipts[0]["request"]["max_tokens"] == plan["config"]["model"]["max_tokens"]
                    and read_json(parent / "api/calls" / (receipts[0]["request_hash"] + ".json")) == receipts[0],
                    "Original request/service/API cache differs")
            _validate_original(receipts[0], score, plan, fixture=data["fixture"])
            detail = _detail_text(score["metrics"].get("details", {}))
            calls.extend(receipts)
            slots.append({"position": base.name, "task_hash": digest(task), "repeat": repeat,
                          "prediction_hash": prediction["record_hash"], "old_score_hash": score["record_hash"],
                          "old_status": score["status"], "old_reason": score["reason"],
                          "old_nltk_resource_missing": bool(re.search(r"Resource\s+(?:punkt|stopwords)\s+not found", detail))})
    positions = {s["position"] for s in slots}
    require({p.stem for p in (parent / "host_only/scores").glob("*.json")} == positions
            and {p.name for p in (parent / "predictions").iterdir() if p.is_dir()} == positions, "Original roster differs")
    reports = [read_json(p, sealed=True) for p in (parent / "host_only/reports").glob("*.json")]
    reports = [r for r in reports if r["plan_hash"] == plan["record_hash"] and r["run_accounting"]["scored_positions"] == 800]
    require(len(reports) == 1 and all(reports[0]["run_accounting"][k] == v for k, v in _costs(calls).items()),
            "Original complete report/accounting missing")
    files = {str(p): reference._sha(p) for p in parent.rglob("*.json")}
    return data, seal({"version": VERSION, "qualification_root": str(qualification), "parent_root": str(parent),
        "qualification_protocol_hash": qprotocol["record_hash"], "qualification": authorization,
        "source_identity": source_identity(), "original_files": files, "slots": slots, "runtime": data["runtime"],
        "native_lock": qprotocol["native_lock"], "original_model_accounting": reports[0]["run_accounting"],
        "model_calls": 0, "old_scores_replaced": False, "skill_gate_allowed": False,
        "evidence_kind": "engineering_fixture" if data["fixture"] else "frozen_model_predictions_environment_rescore"})


def prepare(qualification, output):
    qualification, root = safe_path(qualification), safe_path(output)
    require(not root.exists(), "New rescore directory required")
    _, _, parent, _ = _qualified(qualification)
    require(not any(root.is_relative_to(p) or p.is_relative_to(root) for p in (qualification, parent)),
            "Independent output required")
    with reference._lock(parent / ".writer.lock", shared=True):
        _, protocol = _snapshot(qualification)
        write_json(root / "protocol.json", protocol)
    return protocol


def _load(root):
    protocol = read_json(root / "protocol.json", sealed=True)
    data, actual = _snapshot(safe_path(protocol["qualification_root"]))
    require(protocol == actual, "Frozen rescore evidence/source changed")
    return protocol, data


def _rows(root, protocol, data):
    requests = {s["position"]: {"protocol_hash": protocol["record_hash"], "slot": s} for s in protocol["slots"]}
    intents, rows = {}, {}
    for path in (root / "intents").glob("*.json"):
        require(path.stem in requests and read_json(path, sealed=True) == seal(requests[path.stem]), "Rescore intent differs")
        intents[path.stem] = requests[path.stem]
    for path in (root / "records").glob("*.json"):
        row = read_json(path, sealed=True)
        require(path.stem in intents and row["request"] == intents[path.stem], "Rescore receipt differs")
        reference._validated_score(row["score"], data)
        rows[path.stem] = row
    for path in (root / "reports").glob("*.json"):
        prior = read_json(path, sealed=True)
        require(prior["protocol_hash"] == protocol["record_hash"] and path.stem == prior["record_hash"]
                and all(k in rows and rows[k]["record_hash"] == v for k, v in prior["record_hashes"].items()),
                "Previously published rescore changed")
    return intents, rows


def _report(root, protocol, data):
    intents, rows = _rows(root, protocol, data)
    costs = [r["score"].get("execution_costs", {}) for r in rows.values()]
    counts = Counter(r["score"]["status"] for r in rows.values())
    strata = {}
    for name, flag in (("old_explicit_nltk_missing", True), ("all_other_original_positions", False)):
        selected = [s for s in protocol["slots"] if s["old_nltk_resource_missing"] == flag]
        done = [rows[s["position"]] for s in selected if s["position"] in rows]
        strata[name] = {"positions": len(selected), "tasks": len({s["task_hash"] for s in selected}),
                       "closed": len(done), "counts": dict(Counter(r["score"]["status"] for r in done)),
                       "old_to_new": dict(Counter(r["request"]["slot"]["old_status"] + "__" + r["score"]["status"] for r in done))}
    return seal({"version": VERSION, "protocol_hash": protocol["record_hash"],
        "status": "completed" if len(rows) == 800 and not any(_unsafe(r["score"], data) for r in rows.values()) else "pending",
        "tasks": 400, "families": 399, "positions": 800,
        "closed": len(rows), "unclosed": len(intents) - len(rows), "unsubmitted": 800 - len(intents),
        "counts": dict(counts), "old_to_new": dict(Counter(r["request"]["slot"]["old_status"] + "__" + r["score"]["status"]
                                                          for r in rows.values())),
        "predeclared_environment_diagnostic_strata": strata,
        "model_calls": 0, "container_calls_known_subtotal": sum(c.get("container_calls", 0) for c in costs),
        "container_wall_seconds_known_subtotal": round(sum(c.get("wall_seconds", 0) for c in costs), 6),
        "costs_complete": len(intents) == len(rows) and all("container_calls" in c and "wall_seconds" in c for c in costs)
            and not any(_unsafe(r["score"], data) for r in rows.values()),
        "cleanup_confirmed": sum(r["score"].get("cleanup_confirmed") is True for r in rows.values()),
        "record_hashes": {k: r["record_hash"] for k, r in rows.items()}, "evidence_kind": protocol["evidence_kind"],
        "old_scores_replaced": False, "skill_gate_allowed": False,
        "interpretation": "Frozen-output environment comparison; repeated native execution may add runtime variability, not Skill benefit.",
        "limitations": ["Old native-timeout changes are not evidence that NLTK data repaired them.",
                        "Old learning scores/gates remain unchanged; new-environment No-Skill is not an environment-matched learner comparison."]})


def _unsafe(score, data):
    return score["reason"] in {"host_scorer_exception", "container_cleanup_unconfirmed"} or (
        not data["fixture"] and score["reason"] != "original_prediction_unavailable" and score.get("cleanup_confirmed") is not True)


def run(output, *, max_new_positions=None, fixture_score=None):
    root = safe_path(output)
    initial = read_json(root / "protocol.json", sealed=True)
    require(max_new_positions is None or type(max_new_positions) is int and 0 <= max_new_positions <= 800, "Invalid run bound")
    with output_lock(root), reference._lock(safe_path(initial["parent_root"]) / ".writer.lock", shared=True), \
            reference._lock(safe_path(initial["native_lock"])):
        protocol, data = _load(root)
        require(data["fixture"] == (fixture_score is not None), "Fixture boundary")
        intents, rows = _rows(root, protocol, data)
        if (root / "result.json").exists():
            result = read_json(root / "result.json", sealed=True)
            require(result == _report(root, protocol, data), "Terminal rescore changed")
            return result
        if set(intents) - set(rows) or any(_unsafe(r["score"], data) for r in rows.values()):
            return _report(root, protocol, data)
        tasks = {r["identity"]["task_hash"]: r["task"] for r in data["references"]}
        count = 0
        for slot in protocol["slots"]:
            key = slot["position"]
            if key in rows:
                continue
            if (root / "PAUSE").exists() or max_new_positions is not None and count >= max_new_positions:
                break
            request = {"protocol_hash": protocol["record_hash"], "slot": slot}
            write_json(root / "intents" / (key + ".json"), seal(request))
            prediction = read_json(safe_path(protocol["parent_root"]) / "predictions" / key / "prediction.json", sealed=True)
            require(prediction["record_hash"] == slot["prediction_hash"], "Original prediction changed")
            task = tasks[slot["task_hash"]]
            try:
                if prediction["prediction"]["status"] == "unknown":
                    score = {"status": "unknown", "score": None, "reason": "original_prediction_unavailable", "metrics": {},
                             "execution_costs": {"container_calls": 0, "wall_seconds": 0}}
                else:
                    score = (fixture_score or backends.score)("bigcodebench", task["public"], task["private"],
                                                              prediction["prediction"], runtime=data["runtime"])
                score = reference._validated_score(score, data)
            except Exception:
                score = {"status": "unknown", "score": None, "reason": "host_scorer_exception", "metrics": {}}
            write_json(root / "records" / (key + ".json"), seal({"request": request, "score": score}))
            count += 1
            if _unsafe(score, data):
                break
        result = _report(root, protocol, data)
        write_json(root / "reports" / (result["record_hash"] + ".json"), result)
        if result["status"] == "completed":
            write_json(root / "result.json", result)
        return result


def main(argv=None):
    import json

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("prepare", "check", "run"))
    parser.add_argument("--output", required=True)
    parser.add_argument("--qualification")
    args = parser.parse_args(argv)
    if args.mode == "prepare":
        require(args.qualification, "Completed new-image qualification required")
        value = prepare(args.qualification, args.output)
    elif args.mode == "check":
        value, _ = _load(safe_path(args.output))
    else:
        value = run(args.output)
    print(json.dumps({k: value[k] for k in ("version", "record_hash", "status", "counts", "closed", "unsubmitted", "model_calls") if k in value}))


if __name__ == "__main__":
    main()
