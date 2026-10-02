"""Full frozen Sheet extraction audit and zero-API, once-only parser replay.

Use the original frozen skillopt package/interpreter. Audit every position,
including known pass/fail; execute only preregistered old unknowns whose closed
stop reply yields a different literal deliverable. Neither code nor prompts
are repaired. The qualified original scorer remains unchanged. New artifacts
are private; reports contain hashes/counts rather than model code or workbooks.
"""
from __future__ import annotations

import argparse
import base64
import fcntl
import hashlib
import importlib.util
import json
from collections import Counter
from pathlib import Path

try:  # Direct deployed sibling scripts, or repository module invocation.
    import replay_native_unknowns as native
except ModuleNotFoundError:
    from scripts import replay_native_unknowns as native

from skillopt.coevolution_v5.core import seal
from skillopt.continual_eval import backends
from skillopt.continual_eval.core import output_lock, panel_tasks, read_json, require, safe_path, write_json
from skillopt.continual_eval.runner import _valid_score
from skillopt.validator_pilot.api import digest

VERSION = "frozen-fenced-delivery-replay-v1"


def _parser(path):
    path = safe_path(path)
    spec = importlib.util.spec_from_file_location("frozen_fence_parser_" + native.sha(path), path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    require(module.VERSION == "explicit-python-fences-v1", "Unexpected parser version")
    return module


def _audit(parent, parser):
    plan = read_json(parent / "plan.json", sealed=True)
    rows = []
    for path in sorted((parent / "predictions").glob("*/prediction.json")):
        prediction = read_json(path, sealed=True)
        value = prediction["prediction"]
        call = read_json(next((path.parent / "calls").glob("*.json")), sealed=True)
        receipt = call["receipt"]
        score = read_json(parent / "host_only/scores" / (path.parent.name + ".json"), sealed=True)
        raw = receipt.get("response")
        closed = (receipt.get("ok") is True and receipt.get("status") == 200
            and receipt.get("finish_reason") == "stop" and receipt.get("stream_complete") is True
            and receipt.get("returned_model") == plan["config"]["model"]["name"] and type(raw) is str)
        old = value["output"]["code"] if value["status"] == "available" else None
        if old is not None:
            require(closed and old == backends._code(raw), "Original code differs from closed frozen response")
        parsed = parser.extract_python(raw) if closed else None
        code = parsed["code"] if parsed and parsed["status"] == "available" else None
        # Old extraction already stripped exterior whitespace. Keep the new
        # payload literal, but do not count its retained final newline as a fix.
        changed = old is not None and code is not None and old != code.strip()
        rows.append({"position": path.parent.name, "task_hash": prediction["request"]["task_hash"],
            "repeat": prediction["request"]["repeat"], "prediction_hash": prediction["record_hash"],
            "call_hash": call["record_hash"], "score_hash": score["record_hash"],
            "original_status": score["status"], "closed_stop": closed,
            "raw_sha256": parsed["source_sha256"] if parsed else None,
            "old_code_sha256": hashlib.sha256(old.encode()).hexdigest() if old is not None else None,
            "parser": {k: v for k, v in parsed.items() if k != "code"} if parsed else None,
            "code_bytes_changed": old is not None and code is not None and old != code,
            "substantive_extraction_changed": changed,
            "eligible": changed and score["status"] == "unknown"})
    require(len(rows) == len(plan["tasks"]) * plan["repeats"], "Full extraction audit denominator differs")
    return rows


def _qualification(runtime, fixture):
    if fixture:
        return None
    from skillopt.continual_eval.sheet_recalc_adapter import qualified_engine
    _, qualified = qualified_engine(runtime)  # Source/path authorization only, no container.
    return {"record_hash": qualified["record_hash"], "engine": qualified["engine"]}


def _input_hashes(plan, fixture):
    """Pin public bytes; only explicitly authored fixtures may lack asset pins."""
    hashes = {}
    for task in panel_tasks(plan, "spreadsheetbench"):
        for path in task["public"]["input_files"]:
            expected = task["private"].get("asset_sha256", {}).get(path)
            require(expected is not None or fixture, "Natural public workbook requires frozen asset hash")
            actual = native.sha(path)
            require(expected is None or expected == actual, "Public workbook differs from frozen asset hash")
            require(path not in hashes or hashes[path] == actual, "Conflicting public workbook hashes")
            hashes[path] = actual
    return hashes


def _input_bytes(value, path):
    """Hash the exact bounded bytes sent to Docker, not an earlier file read."""
    with safe_path(path).open("rb") as handle:
        raw = handle.read(backends.MAX_WORKBOOK + 1)
    require(len(raw) <= backends.MAX_WORKBOOK, "Public workbook size limit")
    require(hashlib.sha256(raw).hexdigest() == value["public_input_sha256"].get(path),
            "Public workbook changed before execution")
    return raw


def _execution_sources(value, plan):
    """Recheck execution code after waiting and immediately before each case."""
    require(value["script_sha256"] == native.sha(__file__)
            and value["native_script_sha256"] == native.sha(native.__file__)
            and value["wrapper_sha256"] == native.sha(native.WORKER)
            and value["parser_sha256"] == native.sha(value["parser_path"]), "Diagnostic source identity changed")
    require(plan["source_identity"] == native.source_identity(), "Frozen execution source changed")
    source = safe_path(value["source"])
    for name, expected in plan["source_identity"].items():
        path = safe_path(source / "skillopt" / name)
        require(path.is_relative_to(source / "skillopt") and native.sha(path) == expected,
                "Frozen execution source changed")


def prepare(parent, source, output, native_lock, parser_path):
    parent, source, root, lock, parser_path = map(safe_path, (parent, source, output, native_lock, parser_path))
    require(not root.exists() and not any(root.is_relative_to(p) or p.is_relative_to(root)
                                        for p in (parent, source)), "New independent output required")
    require(lock.is_file() and not any(lock.is_relative_to(p) for p in (parent, source, root)),
            "Existing external shared native lock required")
    with native.parent_lock(parent):
        snapshot = native._snapshot(parent, source)
        require(snapshot["benchmark"] == "spreadsheetbench", "Spreadsheet-only parser diagnostic")
        parser = _parser(parser_path)
        plan = read_json(parent / "plan.json", sealed=True)
        audit = _audit(parent, parser)
        value = seal({"version": VERSION, "parent": str(parent), "source": str(source), "output": str(root),
            "native_lock": str(lock), "parser_path": str(parser_path), "parser_sha256": native.sha(parser_path),
            "script_sha256": native.sha(__file__), "native_script_sha256": native.sha(native.__file__),
            "wrapper_sha256": native.sha(native.WORKER), "snapshot": snapshot, "audit": audit,
            "public_input_sha256": _input_hashes(plan, snapshot["fixture"]),
            "qualification": _qualification(plan["config"]["runtime"]["spreadsheetbench"], snapshot["fixture"]),
            "selection": "all_original_unknown_closed_stop_with_substantive_literal_extraction_change",
            "new_model_calls": 0, "old_scores_replaced": False, "feedback_allowed": False})
        root.mkdir(parents=True, mode=0o700)
        write_json(root / "protocol.json", value)
        return {"status": "prepared", "record_hash": value["record_hash"], "audited": len(audit),
                "selected": sum(r["eligible"] for r in audit)}


def check(output):
    root = safe_path(output)
    value = read_json(root / "protocol.json", sealed=True)
    require(value["version"] == VERSION and value["output"] == str(root)
            and value["script_sha256"] == native.sha(__file__)
            and value["native_script_sha256"] == native.sha(native.__file__)
            and value["wrapper_sha256"] == native.sha(native.WORKER)
            and value["parser_sha256"] == native.sha(value["parser_path"]), "Diagnostic source identity changed")
    parent, source = safe_path(value["parent"]), safe_path(value["source"])
    with native.parent_lock(parent):
        require(native._snapshot(parent, source) == value["snapshot"]
                and _audit(parent, _parser(value["parser_path"])) == value["audit"], "Original frozen evidence changed")
        plan = read_json(parent / "plan.json", sealed=True)
        require(_input_hashes(plan, value["snapshot"]["fixture"]) == value["public_input_sha256"],
                "Public workbook bindings changed")
        require(_qualification(plan["config"]["runtime"]["spreadsheetbench"], value["snapshot"]["fixture"])
                == value["qualification"], "Original qualification changed")
    return value


def _cleanup_bad(result):
    return result.get("cleanup_confirmed") is False or "container_cleanup_unconfirmed" in result.get("reason", "")


def _record(root, value, item):
    path = root / "records" / (item["position"] + ".json")
    if not path.exists():
        return None
    row = read_json(path, sealed=True)
    identity = {"protocol_hash": value["record_hash"], "item": item}
    require(row["identity"] == identity and read_json(root / "intents" / path.name, sealed=True) == seal(identity),
            "Replay record/intent binding differs")
    require(len(row["case_record_hashes"]) == len(row["cases"]), "Case denominator changed")
    for index, expected in enumerate(row["case_record_hashes"]):
        require(read_json(root / "cases" / item["position"] / f"{index}.json", sealed=True)["record_hash"] == expected,
                "Case evidence changed")
    _valid_score(row["score"])
    return row


def report(output):
    root = safe_path(output)
    value = check(root)
    for path in (root / "reports").glob("*.json"):
        old = read_json(path, sealed=True)
        require(old["protocol_hash"] == value["record_hash"], "Published report protocol differs")
        for position, expected in old["record_hashes"].items():
            require(read_json(root / "records" / (position + ".json"), sealed=True)["record_hash"] == expected,
                    "Published replay record changed")
    selected = [r for r in value["audit"] if r["eligible"]]
    rows = [row for item in selected if (row := _record(root, value, item)) is not None]
    bad = any(r["cleanup_unconfirmed"] for r in rows)
    costs = [case.get("execution_costs", {}) for r in rows for case in r["cases"]]
    costs += [r["score"].get("execution_costs", {}) for r in rows]
    return seal({"version": VERSION, "protocol_hash": value["record_hash"],
        "status": "blocked" if bad else "completed" if len(rows) == len(selected) else "pending",
        "original_positions": len(value["audit"]), "selected": len(selected), "completed": len(rows),
        "extraction_changes_by_original_status": dict(Counter(r["original_status"] for r in value["audit"]
            if r["substantive_extraction_changed"])),
        "parser_outcomes": dict(Counter(r["parser"]["reason"] if r["parser"] else "not_closed_stop" for r in value["audit"])),
        "byte_changed": sum(r["code_bytes_changed"] for r in value["audit"]),
        "delivery_case_status": dict(Counter(c["status"] for r in rows for c in r["cases"])),
        "semantic_scores": dict(Counter(r["score"]["status"] for r in rows)),
        "native_container_calls": sum(c.get("container_calls", 0) for c in costs),
        "native_wall_seconds": sum(c.get("wall_seconds", 0.) for c in costs),
        "cleanup_unconfirmed": bad, "new_model_calls": 0,
        "record_hashes": {r["identity"]["item"]["position"]: r["record_hash"] for r in rows},
        "old_scores_replaced": False, "feedback_allowed": False, "whole_baseline_regraded": False,
        "evidence_kind": "engineering_fixture" if value["snapshot"]["fixture"] else "frozen_delivery_parser_diagnostic"})


def run(output, *, fixture_execute=None, fixture_score=None):
    root = safe_path(output)
    with output_lock(root):
        value = check(root)
        fixture = value["snapshot"]["fixture"]
        require((fixture and fixture_execute is not None and fixture_score is not None)
                or (not fixture and fixture_execute is None and fixture_score is None), "Fixture dispatch mismatch")
        report(root)
        parent, source = Path(value["parent"]), Path(value["source"])
        plan = read_json(parent / "plan.json", sealed=True)
        runtime = plan["config"]["runtime"]["spreadsheetbench"]
        tasks = {digest(t): t for t in panel_tasks(plan, "spreadsheetbench")}
        parser = _parser(value["parser_path"])
        with native.parent_lock(parent), safe_path(value["native_lock"]).open("rb") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            # The shared lock can wait behind a long native job. Validate again
            # before recording an intent, not merely when the wait began.
            require(check(root) == value, "Frozen evidence changed while waiting for native lock")
            for item in (r for r in value["audit"] if r["eligible"]):
                old = _record(root, value, item)
                if old is not None:
                    require(not old["cleanup_unconfirmed"], "Prior cleanup unconfirmed; stop replay")
                    continue
                identity = {"protocol_hash": value["record_hash"], "item": item}
                intent = root / "intents" / (item["position"] + ".json")
                require(not intent.exists(), "Open replay intent; no automatic reexecution")
                base = parent / "predictions" / item["position"]
                raw = read_json(next((base / "calls").glob("*.json")), sealed=True)["receipt"]["response"]
                parsed = parser.extract_python(raw)
                require({k: v for k, v in parsed.items() if k != "code"} == item["parser"], "Extraction changed")
                code = parsed["code"]
                task = tasks[item["task_hash"]]
                write_json(intent, seal(identity))
                cases = []
                for index, path in enumerate(task["public"]["input_files"]):
                    if any(_cleanup_bad(c) for c in cases):
                        result = {"status": "unknown", "reason": "not_executed_after_cleanup_failure"}
                        cases.append(result)
                        write_json(root / "cases" / item["position"] / f"{index}.json", seal(result))
                        continue
                    _execution_sources(value, plan)
                    require(hashlib.sha256(code.encode("utf-8")).hexdigest() == item["parser"]["code_sha256"],
                            "Extracted code changed before execution")
                    request = {"operation": "spreadsheet_generate", "code": code,
                               "input_base64": base64.b64encode(_input_bytes(value, path)).decode()}
                    result = fixture_execute(request, runtime) if fixture else native.sheet_native(request, runtime,
                        source / "skillopt/continual_eval/native_worker.py")
                    native._validate_result(result, "spreadsheetbench", fixture, runtime)
                    cases.append(result)
                    write_json(root / "cases" / item["position"] / f"{index}.json", seal(result))
                prediction = {"status": "available", "output": {"code": code, "cases": cases},
                              "reason": "unchanged_literal_reply_reextracted", "costs": {"calls": 0}}
                if any(_cleanup_bad(c) for c in cases):
                    score = {"status": "unknown", "score": None, "metrics": {}, "reason": "container_cleanup_unconfirmed"}
                else:
                    request = {"benchmark": "spreadsheetbench", "protocol_hash": value["record_hash"],
                               "original_position": item["position"], "task_hash": item["task_hash"], "repeat": item["repeat"]}
                    key = digest(request)
                    score_runtime = {**runtime, "_score_context": {
                        "artifact_dir": str(root / "host_only/scorer_artifacts" / key), "position": key,
                        "request": request, "prediction_hash": digest(prediction)}}
                    scorer = fixture_score or backends.score
                    score = _valid_score(scorer("spreadsheetbench", task["public"], task["private"],
                                               prediction, runtime=score_runtime))
                row = seal({"identity": identity, "cases": [{k: v for k, v in c.items() if k != "output_base64"}
                    for c in cases], "score": score, "cleanup_unconfirmed": any(_cleanup_bad(c) for c in [*cases, score]),
                    "case_record_hashes": [seal(c)["record_hash"] for c in cases],
                    "new_model_calls": 0, "old_scores_replaced": False})
                write_json(root / "records" / (item["position"] + ".json"), row)
                result = report(root)
                write_json(root / "reports" / (result["record_hash"] + ".json"), result)
                require(not row["cleanup_unconfirmed"], "Native cleanup unconfirmed; stop replay")
    return report(root)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "run", "report"))
    parser.add_argument("--output", required=True)
    parser.add_argument("--parent")
    parser.add_argument("--source")
    parser.add_argument("--native-lock")
    parser.add_argument("--parser-path")
    args = parser.parse_args(argv)
    if args.command == "prepare":
        require(all((args.parent, args.source, args.native_lock, args.parser_path)), "Prepare arguments missing")
        result = prepare(args.parent, args.source, args.output, args.native_lock, args.parser_path)
    else:
        result = run(args.output) if args.command == "run" else report(args.output)
    print(json.dumps(result, indent=2))
    return 0 if result["status"] in {"prepared", "completed"} else 3


if __name__ == "__main__":
    raise SystemExit(main())
