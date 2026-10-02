"""One diagnostic opportunity for closed full-panel delivery failures.

Run with the original frozen skillopt package on PYTHONPATH. This script does
not alter any baseline. KOR length and provider-network strata are separate;
SearchQA safety-filtered calls are archived, never resubmitted. Spreadsheet is
deliberately unsupported until its qualification/scoring lineage is adapted.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
from collections import Counter
from pathlib import Path

from skillopt.coevolution_v5.core import seal
from skillopt.continual_eval import backends
from skillopt.continual_eval.core import (
    load_checkpoint,
    output_lock,
    panel_tasks,
    read_json,
    require,
    runtime_identity,
    safe_path,
    source_identity,
    write_json,
)
from skillopt.continual_eval.runner import _costs, _stored_calls, _valid_prediction, _valid_score
from skillopt.continual_eval.truncation_recovery import _pause_signals, _readonly_parent_lock
from skillopt.validator_pilot.api import CachedAPI, digest, long_stream_service

VERSION = "full-panel-delivery-recovery-v1"
PROFILES = {"length": (131072, 3600), "network_error": (65536, 1800), "archive_filters": (None, None)}


def _sha(path):
    return hashlib.sha256(safe_path(path).read_bytes()).hexdigest()


def _snapshot(parent, source, reason):
    plan = read_json(parent / "plan.json", sealed=True)
    model = plan["config"]["model"]
    fixture = model["provider"] == "fixture"
    require(plan["version"] == "continual-eval-v2" and plan["config"]["partition"] == "development"
            and plan["config"]["methods"] == ["no_skill"] and plan["config"]["histories"] == ["h0"]
            and plan["repeats"] == 2, "Only full closed development No-Skill runs supported")
    benchmarks = {t["benchmark"] for t in plan["tasks"]}
    require(len(benchmarks) == 1 and benchmarks <= {"korbench", "searchqa"},
            "Only KOR/SearchQA supported; Spreadsheet qualification adapter is pending")
    benchmark = next(iter(benchmarks))
    require({digest(t) for t in panel_tasks(plan, benchmark)} == {t["task_hash"] for t in plan["tasks"]},
            "Panel differs from frozen task roster")
    require((benchmark == "searchqa") == (reason == "archive_filters"), "Unsupported benchmark/recovery stratum")
    require(fixture or len(plan["tasks"]) == {"korbench": 500, "searchqa": 400}[benchmark],
            "Full natural panel required")
    require(model["max_tokens"] == 65536 and model["transport"] == {
        "stream": True, "read_timeout_seconds": 300, "stream_wall_seconds": 1800,
        "initial_health_policy": "completed_response_v1"}, "Unexpected original delivery profile")
    require(fixture or (model["provider"] == "bigmodel" and model["name"] == "glm-5.3"),
            "Only the frozen GLM-5.3 service is supported")
    require(plan["source_identity"] == source_identity() and plan["host_runtime"] == runtime_identity(),
            "Use original frozen evaluation package/runtime")
    for name, expected in plan["source_identity"].items():
        path = safe_path(source / "skillopt" / name)
        require(path.is_relative_to(source / "skillopt") and _sha(path) == expected, "Frozen source changed")
    cp = load_checkpoint(parent, "no_skill", "h0", 0, plan)
    require(cp["skill_text"] == "", "Empty No-Skill checkpoint required")
    service = read_json(parent / "model_service.json", sealed=True)
    service.pop("record_hash")
    selected, blocked, excluded, calls, positions, caches = [], [], Counter(), [], set(), set()
    for task in plan["tasks"]:
        require(task["partition"] == "development", "Final data forbidden")
        for repeat in range(2):
            request = {"plan_hash": plan["record_hash"], "checkpoint_hash": cp["record_hash"],
                       "benchmark": benchmark, "task_hash": task["task_hash"], "repeat": repeat}
            key = digest(request)
            require(key not in positions, "Duplicate task/repeat identity")
            positions.add(key)
            base = parent / "predictions" / key
            receipts = _stored_calls(base)
            require(len(receipts) == 1 and len(list((base / "call_intents").iterdir())) == 1
                    and len(list((base / "calls").iterdir())) == 1, "Missing, extra or open call")
            call_path = next((base / "calls").glob("*.json"))
            call, receipt = read_json(call_path, sealed=True), receipts[0]
            require(call["request"]["position"] == request and call["request"]["turn"] == 0
                    and receipt["request"]["max_tokens"] == model["max_tokens"]
                    and receipt["request"]["model"] == model["name"]
                    and receipt["request"]["service"] == service, "Original call binding differs")
            require(type(receipt.get("ok")) is bool and type(receipt.get("http_attempt_count")) is int
                    and receipt["http_attempt_count"] >= 1
                    and (not receipt["ok"] or receipt.get("returned_model") == model["name"]),
                    "Invalid terminal receipt")
            cache = parent / "api/calls" / (receipt["request_hash"] + ".json")
            require(read_json(cache) == receipt and cache.name not in caches, "API cache differs/duplicated")
            caches.add(cache.name)
            prediction = read_json(base / "prediction.json", sealed=True)
            require(prediction["request"] == request and prediction["costs"] == _costs(receipts)
                    and read_json(base / "intent.json", sealed=True) == seal(request), "Prediction binding differs")
            _valid_prediction(prediction["prediction"])
            score = read_json(parent / "host_only/scores" / (key + ".json"), sealed=True)
            require(score["prediction_hash"] == prediction["record_hash"]
                    and score["plan_hash"] == plan["record_hash"] and score["checkpoint_hash"] == cp["record_hash"]
                    and score["task_id"] == task["task_id"] and score["repeat"] == repeat
                    and score["costs"] == _costs(receipts)
                    and read_json(parent / "host_only/score_intents" / (key + ".json"), sealed=True)
                    == seal({"request": request, "prediction_hash": prediction["record_hash"]}), "Score binding differs")
            calls.append(receipt)
            finish = receipt.get("finish_reason")
            item = {"position": key, "task_hash": task["task_hash"], "repeat": repeat,
                    "call_path": str(call_path.relative_to(parent)), "call_hash": call["record_hash"],
                    "prediction_hash": prediction["record_hash"], "score_hash": score["record_hash"],
                    "finish_reason": finish}
            if finish in {"sensitive", "content_filter"}:
                require(score["status"] == "unknown", "Filtered source score is not unknown")
                blocked.append({**item, "reason": "provider_safety_filter_no_retry"})
            elif finish == reason and reason != "archive_filters":
                require(score["status"] == prediction["prediction"]["status"] == "unknown"
                        and receipt.get("ok") is False and receipt.get("status") == 200
                        and receipt.get("stream_complete") is True
                        and receipt.get("returned_model") == model["name"], "Recovery needs closed HTTP-200 failure")
                expected_reason = "model_response_truncated" if reason == "length" else "model_call_unavailable"
                require(prediction["prediction"].get("reason") == score["reason"] == expected_reason,
                        "Failure mechanism differs")
                require(reason != "length" or receipt.get("error_type") == "truncated_content",
                        "Length failure lacks typed truncation receipt")
                require(reason != "network_error" or not receipt.get("response"), "Ambiguous network reply")
                selected.append(item)
            else:
                excluded[finish or "none"] += 1
    require({p.name for p in (parent / "api/calls").iterdir()} == caches
            and {p.stem for p in (parent / "host_only/scores").iterdir()} == positions
            and {p.stem for p in (parent / "host_only/score_intents").iterdir()} == positions
            and {p.name for p in (parent / "predictions").iterdir()} == positions,
            "Unbound or missing original positions/caches")
    reports = [read_json(p, sealed=True) for p in (parent / "host_only/reports").glob("*.json")]
    reports = [r for r in reports if r["plan_hash"] == plan["record_hash"]
               and r["run_accounting"]["scored_positions"] == len(positions)]
    require(len(reports) == 1 and all(reports[0]["run_accounting"][k] == v for k, v in _costs(calls).items()),
            "Unique full closed report/accounting required")
    return {"plan_hash": plan["record_hash"], "report_hash": reports[0]["record_hash"], "benchmark": benchmark,
            "fixture": fixture, "original_positions": len(positions), "selected": selected, "blocked": blocked,
            "excluded_finish_reasons": dict(excluded), "service": service,
            "native_sources_hash": digest(backends._kor_sources(plan["config"]["runtime"][benchmark]))
                if benchmark == "korbench" and not fixture else None,
            "panel_sha256": _sha(plan["panels"][benchmark]["path"]),
            "files": {str(p.relative_to(parent)): _sha(p) for p in parent.rglob("*.json")}}


def prepare(run_root, source_root, output, *, reason, native_lock):
    require(reason in PROFILES, "Unsupported recovery reason")
    parent, source, root, lock = map(safe_path, (run_root, source_root, output, native_lock))
    require(not root.exists() and not any(root.is_relative_to(p) or p.is_relative_to(root)
                                        for p in (parent, source)), "New independent output required")
    require(lock.is_file() and not any(lock.is_relative_to(p) for p in (parent, source, root)),
            "Existing external shared native lock required")
    with _readonly_parent_lock(parent):
        snapshot = _snapshot(parent, source, reason)
        cap, wall = PROFILES[reason]
        value = seal({"version": VERSION, "parent_root": str(parent), "source_root": str(source),
            "output_root": str(root), "native_lock": str(lock), "script_sha256": _sha(__file__),
            "snapshot": snapshot, "reason": reason, "max_tokens": cap,
            "service": long_stream_service(snapshot["service"], read_timeout_seconds=300, stream_wall_seconds=wall)
                if wall is not None else None,
            "max_new_logical_calls": len(snapshot["selected"]), "max_http_attempts_per_call": 3,
            "feedback_allowed": False, "old_scores_replaced": False, "diagnostic_only": True})
        root.mkdir(parents=True, mode=0o700)
        write_json(root / "protocol.json", value)
        return {"status": "prepared", "selected": len(snapshot["selected"]), "blocked": len(snapshot["blocked"]),
                "record_hash": value["record_hash"]}


def check(output):
    root = safe_path(output)
    value = read_json(root / "protocol.json", sealed=True)
    require(value["version"] == VERSION and value["output_root"] == str(root)
            and value["script_sha256"] == _sha(__file__), "Diagnostic identity changed")
    require(value["reason"] in PROFILES, "Invalid recovery stratum")
    cap, wall = PROFILES[value["reason"]]
    expected_service = long_stream_service(value["snapshot"]["service"], read_timeout_seconds=300,
        stream_wall_seconds=wall) if wall is not None else None
    require(value["max_tokens"] == cap and value["service"] == expected_service
            and value["max_new_logical_calls"] == len(value["snapshot"]["selected"])
            and value["max_http_attempts_per_call"] == 3 and value["diagnostic_only"] is True
            and value["old_scores_replaced"] is False and value["feedback_allowed"] is False,
            "Frozen recovery limits/boundaries differ")
    with _readonly_parent_lock(safe_path(value["parent_root"])):
        require(_snapshot(safe_path(value["parent_root"]), safe_path(value["source_root"]), value["reason"])
                == value["snapshot"], "Original evidence changed")
    return value


def _expected(value, item):
    receipt = read_json(Path(value["parent_root"]) / item["call_path"], sealed=True)["receipt"]
    return {**receipt["request"], "kind": VERSION, "key": digest({"protocol": value["record_hash"], "item": item}),
            "max_tokens": value["max_tokens"], "service": value["service"]}


def _row(root, value, item):
    base = root / "positions" / item["position"]
    path = base / "result.json"
    if not path.exists():
        return None
    row = read_json(path, sealed=True)
    require(row["protocol_hash"] == value["record_hash"] and row["item"] == item
            and read_json(base / "intent.json", sealed=True) == seal(_expected(value, item)), "Recovery identity differs")
    call = read_json(base / "call.json", sealed=True)
    expected = _expected(value, item)
    require(call["receipt"]["request"] == expected and call["receipt"]["request_hash"] == digest(expected)
            and row["call_hash"] == call["record_hash"], "Recovery receipt differs")
    require(read_json(root / "api/calls" / (digest(expected) + ".json")) == call["receipt"],
            "Recovery API cache differs")
    _valid_prediction(row["prediction"])
    _valid_score(row["score"])
    return row


def _cleanup_unconfirmed(score):
    # Frozen native backends historically omit the boolean on this error path.
    return score.get("cleanup_confirmed") is False or score.get("reason") == "container_cleanup_unconfirmed"


def _read_only_native_preflight(value, runtime):
    """Inspect existing identity only; readiness() would launch a probe container."""
    require(value["snapshot"]["benchmark"] == "korbench", "Only KOR has recoverable native calls")
    backends._runtime_limits(runtime)
    require(backends._image_ready(runtime)["status"] == "ready", "Original native image unavailable")
    require(digest(backends._kor_sources(runtime)) == value["snapshot"]["native_sources_hash"],
            "Original KOR scorer source changed")


def report(output):
    root = safe_path(output)
    value = check(root)
    for path in (root / "reports").glob("*.json"):
        old = read_json(path, sealed=True)
        require(old["protocol_hash"] == value["record_hash"], "Published protocol differs")
        for key, expected in old["result_hashes"].items():
            require(read_json(root / "positions" / key / "result.json", sealed=True)["record_hash"] == expected,
                    "Published result changed")
    rows, receipts, opened = [], [], 0
    for item in value["snapshot"]["selected"]:
        row = _row(root, value, item)
        base = root / "positions" / item["position"]
        if row is not None:
            rows.append(row)
        if (base / "call.json").exists():
            receipts.append(read_json(base / "call.json", sealed=True)["receipt"])
        elif (base / "intent.json").exists():
            opened += 1
    cleanup_blocked = any(_cleanup_unconfirmed(r["score"]) for r in rows)
    return seal({"version": VERSION, "protocol_hash": value["record_hash"],
        "status": "blocked" if cleanup_blocked else "completed" if len(rows) == value["max_new_logical_calls"] else "pending",
        "blocked_reason": "native_cleanup_unconfirmed" if cleanup_blocked else None,
        "original_positions": value["snapshot"]["original_positions"], "selected": value["max_new_logical_calls"],
        "completed": len(rows), "blocked": len(value["snapshot"]["blocked"]),
        "counts": dict(Counter(r["score"]["status"] for r in rows)), "new_costs": _costs(receipts, unclosed=opened),
        "old_selected_costs": _costs([read_json(Path(value["parent_root"]) / item["call_path"], sealed=True)["receipt"]
            for item in value["snapshot"]["selected"]]),
        "known_reported_tokens": sum(r.get("usage", {}).get(k, 0) for r in receipts
            for k in ("prompt_tokens", "completion_tokens") if type(r.get("usage", {}).get(k)) is int),
        "usage_missing_calls": sum(not all(type(r.get("usage", {}).get(k)) is int
            for k in ("prompt_tokens", "completion_tokens")) for r in receipts),
        "native_execution": {
            "reported_container_calls": sum(r["score"].get("execution_costs", {}).get("container_calls", 0) for r in rows),
            "reported_wall_seconds": sum(r["score"].get("execution_costs", {}).get("wall_seconds", 0.) for r in rows),
            "cleanup_confirmed_results": sum(r["score"].get("cleanup_confirmed") is True for r in rows),
            "cleanup_unconfirmed_results": sum(_cleanup_unconfirmed(r["score"]) for r in rows),
            "container_results_without_explicit_cleanup_flag": sum(
                r["score"].get("execution_costs", {}).get("container_calls", 0) > 0
                and "cleanup_confirmed" not in r["score"] for r in rows),
            "available_predictions_without_execution_cost_record": sum(
                r["prediction"]["status"] == "available" and "execution_costs" not in r["score"] for r in rows)},
        "result_hashes": {r["item"]["position"]: r["record_hash"] for r in rows},
        "evidence_kind": "engineering_fixture" if value["snapshot"]["fixture"] else "selected_closed_delivery_retry_diagnostic",
        "diagnostic_only": True, "old_scores_replaced": False, "feedback_allowed": False,
        "whole_benchmark_accuracy_claimed": False, "causal_token_effect_claimed": False})


def run(output, *, repo=None, fixture_api=None, fixture_solve=None, fixture_score=None):
    root = safe_path(output)
    with output_lock(root), _pause_signals(root) as stopping:
        value = check(root)
        fixture = value["snapshot"]["fixture"]
        require((fixture and all(x is not None for x in (fixture_api, fixture_solve, fixture_score)))
                or (not fixture and all(x is None for x in (fixture_api, fixture_solve, fixture_score))),
                "Fixture dispatch mismatch")
        report(root)  # Verify previously published result bindings before writing.
        pending = []
        for item in value["snapshot"]["selected"]:
            previous = _row(root, value, item)
            require(previous is None or not _cleanup_unconfirmed(previous["score"]),
                    "Prior native cleanup unconfirmed; stop remaining submissions")
            if previous is None:
                require(not (root / "positions" / item["position"]).exists(),
                        "Open recovery intent; do not resample")
                require(not (root / "api/calls" / (digest(_expected(value, item)) + ".json")).exists(),
                        "Unbound recovery cache; do not resample")
                pending.append(item)
        if not pending or stopping():
            return report(root)
        parent = Path(value["parent_root"])
        plan = read_json(parent / "plan.json", sealed=True)
        benchmark = value["snapshot"]["benchmark"]
        runtime = plan["config"]["runtime"].get(benchmark, {})
        tasks = {digest(t): t for t in panel_tasks(plan, benchmark)}
        model, service = plan["config"]["model"], value["service"]
        if not fixture:
            require(repo is not None, "Credential repository required")
            _read_only_native_preflight(value, runtime)
        api = fixture_api if fixture else CachedAPI(Path(repo), root / "api", provider=model["provider"],
            model=model["name"], workers=1, reasoning_effort=model["reasoning_effort"],
            stream=True, read_timeout_seconds=300, stream_wall_seconds=PROFILES[value["reason"]][1],
            initial_health_policy=service["initial_health_policy"],
            **({"proxy": service["proxy"]} if "proxy" in service else {}))
        try:
            require(api.service == service and api.model == model["name"], "Model service differs")
            with _readonly_parent_lock(parent):
                for index, item in enumerate(pending):
                    if stopping():
                        break
                    base = root / "positions" / item["position"]
                    expected = _expected(value, item)
                    receipt = None

                    def callback(system, user):
                        nonlocal receipt
                        require(system == expected["system"] and user == expected["user"], "Original prompt mismatch")
                        require(receipt is None and not (base / "intent.json").exists(), "Only one logical opportunity")
                        write_json(base / "intent.json", seal(expected))
                        response = api.call(system, user, expected["kind"], expected["key"],
                            max_tokens=expected["max_tokens"], repeat=expected["repeat"])
                        require(response.get("request") == expected and response.get("request_hash") == digest(expected)
                                and type(response.get("http_attempt_count")) is int
                                and 1 <= response["http_attempt_count"] <= 3, "New call binding/attempt budget differs")
                        receipt = response
                        write_json(base / "call.json", seal({"receipt": receipt}))
                        return receipt

                    task = tasks[item["task_hash"]]
                    solver, scorer = (fixture_solve, fixture_score) if fixture else (backends.solve, backends.score)
                    prediction = _valid_prediction(solver(benchmark, task["public"], "", callback, runtime=runtime))
                    require(receipt is not None, "Solver call unavailable; retain any open intent without retry")
                    with safe_path(value["native_lock"]).open("rb") as lock:
                        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
                        score = _valid_score(scorer(benchmark, task["public"], task["private"], prediction, runtime=runtime))
                    if not fixture and benchmark == "korbench" and score["status"] != "unknown":
                        require(score.get("runtime_image_id") == runtime["image"]
                                and score.get("cleanup_confirmed") is True, "Native identity/cleanup unverified")
                    row = seal({"protocol_hash": value["record_hash"], "item": item,
                        "call_hash": read_json(base / "call.json", sealed=True)["record_hash"],
                        "prediction": prediction, "score": score, "old_scores_replaced": False})
                    write_json(base / "result.json", row)
                    result = report(root)
                    write_json(root / "reports" / (result["record_hash"] + ".json"), result)
                    if _cleanup_unconfirmed(score):
                        raise ValueError("Native cleanup unconfirmed; stop remaining submissions")
                    if index == 0:
                        require(api._initial_ready(receipt), "First real response unavailable; remaining calls not submitted")
        finally:
            if not fixture:
                api.close()
    return report(root)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "run", "report"))
    parser.add_argument("--output", required=True)
    parser.add_argument("--run-root")
    parser.add_argument("--source-root")
    parser.add_argument("--reason", choices=tuple(PROFILES))
    parser.add_argument("--native-lock")
    parser.add_argument("--repo")
    args = parser.parse_args(argv)
    if args.command == "prepare":
        require(all((args.run_root, args.source_root, args.reason, args.native_lock)), "Prepare arguments missing")
        result = prepare(args.run_root, args.source_root, args.output, reason=args.reason, native_lock=args.native_lock)
    elif args.command == "run":
        result = run(args.output, repo=args.repo)
    else:
        result = report(args.output)
    print(json.dumps(result, indent=2))
    return 0 if result["status"] in {"prepared", "completed"} else 3


if __name__ == "__main__":
    raise SystemExit(main())
