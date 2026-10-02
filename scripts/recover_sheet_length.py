"""One new delivery opportunity for the sole frozen Sheet length failure.

Use the ORIGINAL frozen skillopt package and interpreter on PYTHONPATH. Only
the delivery cap/wall budget changes. Prompts, extraction, public inputs,
generation sandbox and qualified v5 scorer remain unchanged. This diagnostic
never replaces old scores and cannot authorize learning or deployment.
"""
from __future__ import annotations

import argparse
import fcntl
import json
from pathlib import Path

try:
    import replay_fenced_delivery as fenced
    import replay_native_unknowns as native
except ModuleNotFoundError:
    from scripts import replay_fenced_delivery as fenced
    from scripts import replay_native_unknowns as native

from skillopt.coevolution_v5.core import seal
from skillopt.continual_eval import backends
from skillopt.continual_eval.core import output_lock, panel_tasks, read_json, require, safe_path, write_json
from skillopt.continual_eval.runner import _costs, _valid_prediction, _valid_score
from skillopt.continual_eval.truncation_recovery import _pause_signals
from skillopt.validator_pilot.api import CachedAPI, digest, long_stream_service

VERSION = "single-sheet-length-recovery-v1"
BENCHMARK = "spreadsheetbench"


def _sources():
    return {"script": native.sha(__file__), "native": native.sha(native.__file__),
            "fenced": native.sha(fenced.__file__)}


def _snapshot(parent, source):
    snapshot = native._snapshot(parent, source)
    require(snapshot["benchmark"] == BENCHMARK, "Spreadsheet-only diagnostic")
    plan = read_json(parent / "plan.json", sealed=True)
    selected = []
    for path in sorted(parent.glob("predictions/*/prediction.json")):
        prediction = read_json(path, sealed=True)
        call_path = next((path.parent / "calls").glob("*.json"))
        call = read_json(call_path, sealed=True)
        receipt = call["receipt"]
        if receipt.get("finish_reason") != "length":
            continue
        score = read_json(parent / "host_only/scores" / (path.parent.name + ".json"), sealed=True)
        require(receipt.get("ok") is False and receipt.get("status") == 200
                and receipt.get("stream_complete") is True and receipt.get("error_type") == "truncated_content"
                and receipt.get("returned_model") == plan["config"]["model"]["name"]
                and score["status"] == prediction["prediction"]["status"] == "unknown"
                and score["reason"] == prediction["prediction"]["reason"] == "model_response_truncated",
                "Expected a closed typed truncation, not an interrupted call")
        selected.append({"position": path.parent.name, "task_hash": prediction["request"]["task_hash"],
            "repeat": prediction["request"]["repeat"], "call_path": str(call_path.relative_to(parent)),
            "call_hash": call["record_hash"], "prediction_hash": prediction["record_hash"],
            "score_hash": score["record_hash"]})
    require(len(selected) == 1, "This bounded diagnostic requires exactly one closed Sheet length failure")
    tasks = {digest(t): t for t in panel_tasks(plan, BENCHMARK)}
    require(len(tasks[selected[0]["task_hash"]]["public"]["input_files"]) == 1,
            "Single public case required for cleanup-safe unchanged solver replay")
    runtime = plan["config"]["runtime"][BENCHMARK]
    return {"parent": snapshot, "selected": selected[0],
        "public_input_sha256": fenced._input_hashes(plan, snapshot["fixture"]),
        "qualification": fenced._qualification(runtime, snapshot["fixture"])}


def prepare(parent, source, output, native_lock):
    parent, source, root, lock = map(safe_path, (parent, source, output, native_lock))
    require(not root.exists() and not any(root.is_relative_to(p) or p.is_relative_to(root)
                                        for p in (parent, source)), "New independent output required")
    require(lock.is_file() and not any(lock.is_relative_to(p) for p in (parent, source, root)),
            "Existing external shared native lock required")
    with native.parent_lock(parent):
        snapshot = _snapshot(parent, source)
        old = read_json(parent / snapshot["selected"]["call_path"], sealed=True)["receipt"]
        value = seal({"version": VERSION, "parent": str(parent), "source": str(source), "output": str(root),
            "native_lock": str(lock), "sources": _sources(), "snapshot": snapshot, "max_tokens": 131072,
            "service": long_stream_service(old["request"]["service"], read_timeout_seconds=300, stream_wall_seconds=3600),
            "max_new_logical_calls": 1, "max_http_attempts_per_call": 3,
            "diagnostic_only": True, "old_scores_replaced": False, "feedback_allowed": False})
        root.mkdir(parents=True, mode=0o700)
        write_json(root / "protocol.json", value)
        return {"status": "prepared", "selected": 1, "record_hash": value["record_hash"]}


def check(output):
    root = safe_path(output)
    value = read_json(root / "protocol.json", sealed=True)
    require(value["version"] == VERSION and value["output"] == str(root) and value["sources"] == _sources(),
            "Diagnostic source identity changed")
    parent = safe_path(value["parent"])
    with native.parent_lock(parent):
        require(_snapshot(parent, safe_path(value["source"])) == value["snapshot"], "Original evidence changed")
    old = read_json(parent / value["snapshot"]["selected"]["call_path"], sealed=True)["receipt"]
    require(value["max_tokens"] == 131072 and value["max_new_logical_calls"] == 1
            and value["max_http_attempts_per_call"] == 3 and value["diagnostic_only"] is True
            and value["old_scores_replaced"] is False and value["feedback_allowed"] is False
            and value["service"] == long_stream_service(old["request"]["service"],
                read_timeout_seconds=300, stream_wall_seconds=3600), "Frozen limits changed")
    return value


def _expected(value):
    item = value["snapshot"]["selected"]
    old = read_json(Path(value["parent"]) / item["call_path"], sealed=True)["receipt"]["request"]
    return {**old, "kind": VERSION, "key": digest({"protocol": value["record_hash"], "item": item}),
            "max_tokens": value["max_tokens"], "service": value["service"]}


def _receipt(root, value):
    if not (root / "call.json").exists():
        return None
    call = read_json(root / "call.json", sealed=True)
    receipt, expected = call["receipt"], _expected(value)
    require(read_json(root / "intent.json", sealed=True) == seal(expected)
            and receipt["request"] == expected and receipt["request_hash"] == digest(expected)
            and read_json(root / "api/calls" / (digest(expected) + ".json")) == receipt
            and type(receipt.get("ok")) is bool
            and (not receipt["ok"] or receipt.get("returned_model") == expected["model"])
            and type(receipt.get("http_attempt_count")) is int and 1 <= receipt["http_attempt_count"] <= 3,
            "Recovery call binding differs")
    return receipt


def _cleanup_bad(prediction, score):
    cases = (prediction.get("output") or {}).get("cases", [])
    return any(fenced._cleanup_bad(row) for row in [*cases, score])


def _validate_native(prediction, score, runtime, fixture):
    if fixture:
        return
    for case in (prediction.get("output") or {}).get("cases", []):
        if case.get("status") in {"available", "missing_output"}:
            require(case.get("cleanup_confirmed") is True and case.get("runtime_image_id") == runtime["image"],
                    "Generation identity or cleanup unverified")
    if score.get("status") in {"pass", "fail"}:
        require(score.get("cleanup_confirmed") is True
                and score.get("runtime_image_id") == runtime["recalculation"]["image"],
                "Qualified scorer identity or cleanup unverified")


def report(output):
    root, value = safe_path(output), check(output)
    receipt, row = _receipt(root, value), None
    if (root / "result.json").exists():
        row = read_json(root / "result.json", sealed=True)
        require(receipt is not None and row["protocol_hash"] == value["record_hash"]
                and row["call_hash"] == read_json(root / "call.json", sealed=True)["record_hash"],
                "Recovery result binding differs")
        _valid_prediction(row["prediction"])
        _valid_score(row["score"])
        require(row["artifacts"] == {str(p.relative_to(root)): native.sha(p)
            for p in (root / "host_only").rglob("*") if p.is_file()}, "Scorer evidence changed")
    for path in (root / "reports").glob("*.json"):
        old = read_json(path, sealed=True)
        require(old["protocol_hash"] == value["record_hash"] and (old["result_hash"] is None
            or row is not None and old["result_hash"] == row["record_hash"]), "Published result changed")
    bad = row is not None and _cleanup_bad(row["prediction"], row["score"])
    costs = [] if row is None else [c.get("execution_costs", {})
        for c in (row["prediction"].get("output") or {}).get("cases", [])] + [row["score"].get("execution_costs", {})]
    original = read_json(Path(value["parent"]) / value["snapshot"]["selected"]["call_path"], sealed=True)["receipt"]
    return seal({"version": VERSION, "protocol_hash": value["record_hash"], "selected": 1,
        "status": "blocked" if bad else "completed" if row else "pending", "completed": int(row is not None),
        "counts": {row["score"]["status"]: 1} if row else {}, "cleanup_unconfirmed": bad,
        "new_costs": _costs([receipt] if receipt else [], unclosed=int((root / "intent.json").exists() and receipt is None)),
        "old_selected_costs": _costs([original]),
        "native_container_calls": sum(c.get("container_calls", 0) for c in costs),
        "native_wall_seconds": sum(c.get("wall_seconds", 0.) for c in costs),
        "native_accounting_complete": row is not None,
        "result_hash": row["record_hash"] if row else None,
        "evidence_kind": "engineering_fixture" if value["snapshot"]["parent"]["fixture"] else "selected_closed_delivery_retry_diagnostic",
        "diagnostic_only": True, "old_scores_replaced": False, "feedback_allowed": False,
        "whole_benchmark_accuracy_claimed": False, "causal_token_effect_claimed": False})


def run(output, *, repo=None, fixture_api=None, fixture_solve=None, fixture_score=None):
    root = safe_path(output)
    with output_lock(root), _pause_signals(root) as stopping:
        value = check(root)
        fixture = value["snapshot"]["parent"]["fixture"]
        require((fixture and all(x is not None for x in (fixture_api, fixture_solve, fixture_score)))
            or (not fixture and all(x is None for x in (fixture_api, fixture_solve, fixture_score))), "Fixture dispatch mismatch")
        status = report(root)
        if status["completed"] or stopping():
            return status
        require(not (root / "intent.json").exists() and not any((root / "api").rglob("*.json")),
                "Open recovery intent/cache; no automatic resampling or reexecution")
        parent, item = Path(value["parent"]), value["snapshot"]["selected"]
        plan = read_json(parent / "plan.json", sealed=True)
        runtime, model = plan["config"]["runtime"][BENCHMARK], plan["config"]["model"]
        task = next(t for t in panel_tasks(plan, BENCHMARK) if digest(t) == item["task_hash"])
        expected = _expected(value)
        old_receipt = read_json(parent / item["call_path"], sealed=True)["receipt"]
        solver, scorer = (fixture_solve, fixture_score) if fixture else (backends.solve, backends.score)
        seen = []

        def callback(receipt):
            def replay(system, user):
                seen.append((system, user))
                require(seen == [(expected["system"], expected["user"])], "Original prompt mismatch or repeated callback")
                return receipt
            return replay

        # Dry public-prompt reconstruction returns the ORIGINAL truncated
        # receipt, so no generated program can execute before the native lock.
        prediction = solver(BENCHMARK, task["public"], "", callback(old_receipt), runtime=runtime)
        require(seen == [(expected["system"], expected["user"])] and prediction["status"] == "unknown"
                and prediction["reason"] == "model_response_truncated", "Original prompt reconstruction failed")
        if not fixture:
            require(repo is not None, "Credential repository required")
            backends._runtime_limits(runtime)
            require(backends._image_ready(runtime)["status"] == "ready", "Generation image unavailable")
            require(backends._image_ready({"image": runtime["recalculation"]["image"]})["status"] == "ready",
                    "Qualified recalculation image unavailable")
        api = fixture_api if fixture else CachedAPI(Path(repo), root / "api", provider=model["provider"],
            model=model["name"], workers=1, reasoning_effort=model["reasoning_effort"], stream=True,
            read_timeout_seconds=300, stream_wall_seconds=3600,
            initial_health_policy=value["service"]["initial_health_policy"],
            **({"proxy": value["service"]["proxy"]} if "proxy" in value["service"] else {}))
        try:
            require(api.service == value["service"] and api.model == model["name"], "Model service differs")
            with native.parent_lock(parent):
                require(check(root) == value, "Evidence changed before submission")
                if stopping():
                    return report(root)
                write_json(root / "intent.json", seal(expected))
                receipt = api.call(expected["system"], expected["user"], expected["kind"], expected["key"],
                    max_tokens=expected["max_tokens"], repeat=expected["repeat"])
                write_json(root / "call.json", seal({"receipt": receipt}))
                _receipt(root, value)
                with safe_path(value["native_lock"]).open("rb") as lock:
                    fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
                    require(check(root) == value, "Evidence changed while waiting for execution")
                    seen.clear()
                    prediction = _valid_prediction(solver(BENCHMARK, task["public"], "", callback(receipt), runtime=runtime))
                    require(seen == [(expected["system"], expected["user"])], "Original prompt mismatch during execution")
                    _validate_native(prediction, {}, runtime, fixture)
                    if _cleanup_bad(prediction, {}):
                        score = {"status": "unknown", "score": None, "metrics": {}, "reason": "container_cleanup_unconfirmed"}
                    else:
                        request = {"benchmark": BENCHMARK, "protocol_hash": value["record_hash"],
                            "original_position": item["position"], "task_hash": item["task_hash"], "repeat": item["repeat"]}
                        key = digest(request)
                        scoring_runtime = {**runtime, "_score_context": {"artifact_dir": str(root / "host_only/scorer_artifacts" / key),
                            "position": key, "request": request, "prediction_hash": digest(prediction)}}
                        score = _valid_score(scorer(BENCHMARK, task["public"], task["private"], prediction, runtime=scoring_runtime))
                    _validate_native(prediction, score, runtime, fixture)
                    row = seal({"protocol_hash": value["record_hash"],
                        "call_hash": read_json(root / "call.json", sealed=True)["record_hash"],
                        "prediction": prediction, "score": score,
                        "artifacts": {str(p.relative_to(root)): native.sha(p)
                            for p in (root / "host_only").rglob("*") if p.is_file()}})
                    write_json(root / "result.json", row)
                    result = report(root)
                    write_json(root / "reports" / (result["record_hash"] + ".json"), result)
                    return result
        finally:
            if not fixture:
                api.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "run", "report"))
    parser.add_argument("--output", required=True)
    for argument in ("parent", "source", "native-lock", "repo"):
        parser.add_argument("--" + argument)
    args = parser.parse_args(argv)
    if args.command == "prepare":
        require(all((args.parent, args.source, args.native_lock)), "Prepare arguments missing")
        result = prepare(args.parent, args.source, args.output, args.native_lock)
    else:
        result = run(args.output, repo=args.repo) if args.command == "run" else report(args.output)
    print(json.dumps(result, indent=2))
    return 0 if result["status"] in {"prepared", "completed"} else 3


if __name__ == "__main__":
    raise SystemExit(main())
