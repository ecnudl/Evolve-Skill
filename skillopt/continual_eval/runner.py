"""Restartable prediction collection, then separate host-only scoring.

No training/updater/Research callback exists here. An unclosed position remains
an explicit interruption: resume never samples a replacement answer. Only the
operator can close it as unknown (without discarding the paid call receipts).
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from pathlib import Path

from skillopt.coevolution_v5.core import seal
from skillopt.validator_pilot.api import CachedAPI, digest

from .core import (
    checkpoint_path,
    load_checkpoint,
    load_plan,
    output_lock,
    panel_tasks,
    public_view,
    read_json,
    require,
    safe_path,
    write_json,
)


def position(root, checkpoint, benchmark, task, repeat):
    request = {"plan_hash": checkpoint["plan_hash"], "checkpoint_hash": checkpoint["record_hash"],
               "benchmark": benchmark, "task_hash": digest(task), "repeat": repeat}
    key = digest(request)
    return safe_path(root) / "predictions" / key, request


def _costs(receipts, *, unclosed=0):
    unique = {r["request_hash"]: r for r in receipts}
    known = not unclosed and all(type(r.get("usage", {}).get(k)) is int for r in unique.values()
                for k in ("prompt_tokens", "completion_tokens"))
    return {"logical_calls": len(unique) + unclosed,
            "http_attempts": None if unclosed else sum(r.get("http_attempt_count", 0) for r in unique.values()),
            "reported_tokens": sum(r["usage"][k] for r in unique.values()
                                   for k in ("prompt_tokens", "completion_tokens")) if known else None,
            "usage_complete": known,
            "unclosed_calls": unclosed,
            "retry_inclusive_usage_known": known and all(r.get("http_attempt_count") == 1 for r in unique.values())}


def _stored_calls(base):
    folder = safe_path(base) / "calls"
    receipts = []
    for path in sorted(folder.glob("*.json")):
        record = read_json(path, sealed=True)
        intent_path = base / "call_intents" / path.name
        require(intent_path.is_file(), "Model receipt has no matching intent")
        intent = read_json(intent_path, sealed=True)
        require({k: v for k, v in intent.items() if k != "record_hash"} == record["request"]
                and digest(record["request"]) == path.stem, "Model receipt and intent identity mismatch")
        require(record["receipt"].get("request_hash") == digest(record["receipt"].get("request")),
                "Model receipt request hash mismatch")
        outer, inner = record["request"], record["receipt"]["request"]
        require(all(inner.get(k) == outer[k] for k in ("system", "user", "max_tokens"))
                and inner.get("key") == path.stem and inner.get("repeat") == outer["position"]["repeat"]
                and inner.get("kind") == "continual-eval-solver", "Nested model receipt belongs to another position")
        receipts.append(record["receipt"])
    return receipts


def _position_costs(base):
    receipts = _stored_calls(base)
    unclosed = len(list((base / "call_intents").glob("*.json"))) - len(receipts)
    require(unclosed >= 0, "Model receipt has no matching intent")
    return _costs(receipts, unclosed=unclosed)


class PositionCalls:
    """Public prompt callbacks with durable intent, before any paid request."""
    def __init__(self, api, base, request, max_tokens, max_calls):
        self.api, self.base, self.request = api, base, request
        self.max_tokens, self.max_calls, self.index = max_tokens, max_calls, 0

    def __call__(self, system, user):
        require(type(system) is str and type(user) is str and len((system + user).encode()) <= 240000,
                "Invalid or oversized public model prompt")
        require(self.index < self.max_calls, "Frozen per-position model call budget exhausted")
        request = {"position": self.request, "turn": self.index, "system": system, "user": user,
                   "max_tokens": self.max_tokens}
        self.index += 1
        key = digest(request)
        intent = self.base / "call_intents" / (key + ".json")
        terminal = self.base / "calls" / (key + ".json")
        if terminal.exists():
            record = read_json(terminal, sealed=True)
            require(record["request"] == request, "Model callback cache mismatch")
            _stored_calls(self.base)
            return record["receipt"]
        require(not intent.exists(), "Interrupted model request; do not resample")
        write_json(intent, seal(request))
        receipt = self.api.call(system, user, "continual-eval-solver", key,
                                max_tokens=self.max_tokens, repeat=self.request["repeat"])
        expected = {"model": self.api.model, "system": system, "user": user, "kind": "continual-eval-solver",
                    "key": key, "max_tokens": self.max_tokens, "repeat": self.request["repeat"],
                    "service": self.api.service}
        require(receipt.get("request") == expected and receipt.get("request_hash") == digest(expected),
                "Model receipt does not match the frozen public request")
        write_json(terminal, seal({"request": request, "receipt": receipt}))
        return receipt


def _valid_prediction(prediction):
    require(type(prediction) is dict and prediction.get("status") in {"available", "unknown"},
            "Backend must return a typed prediction")
    require("output" in prediction and type(prediction.get("reason")) is str, "Missing prediction output/reason")
    return prediction


def generate(root, *, method, history, stage, benchmark, repo=None, workers=1,
             fixture_solve=None, fixture_call=None):
    from . import backends

    require(type(workers) is int and 1 <= workers <= 10, "Workers must be 1..10")
    root = safe_path(root)
    with output_lock(root):
        plan = load_plan(root)
        checkpoint = load_checkpoint(root, method, history, stage, plan)
        tasks = panel_tasks(plan, benchmark)
        require(tasks, "No tasks in requested evaluation partition")
        model = plan["config"]["model"]
        is_fixture = model["provider"] == "fixture"
        require(is_fixture == (fixture_solve is not None), "Fixture callbacks cannot run a natural-data protocol")
        runtime = dict(plan["config"]["runtime"].get(benchmark, {}))
        from .datasets import load_panel
        from .datasets import readiness as data_readiness
        data_state = data_readiness(load_panel(plan["panels"][benchmark]["path"]))
        if not is_fixture:
            require(data_state["status"] == "ready", "Dataset assets are not ready")
            state = backends.readiness(benchmark, runtime)
            require(state["status"] == "ready", "Backend is not ready: " + str(state.get("reason", state)))
        slots = [(task, repeat) for task in tasks for repeat in range(plan["repeats"])]
        # Detect ambiguous interrupted work before opening a provider client.
        for task, repeat in slots:
            base, request = position(root, checkpoint, benchmark, task, repeat)
            if (base / "intent.json").exists() and not (base / "prediction.json").exists():
                raise ValueError("Interrupted position " + base.name + "; inspect receipts or close as unknown")
        pending = [(task, repeat) for task, repeat in slots
                   if not (position(root, checkpoint, benchmark, task, repeat)[0] / "prediction.json").exists()]
        api = None
        if pending and not is_fixture:
            require(repo is not None, "Repository path required for provider-specific local .env")
            api = CachedAPI(Path(repo), root / "api", provider=model["provider"], model=model["name"],
                            workers=workers, reasoning_effort=model["reasoning_effort"],
                            **model.get("transport", {"initial_health_policy": "completed_response_v1"}),
                            **({"proxy": model["proxy"]} if "proxy" in model else {}))
            write_json(root / "model_service.json", seal(api.service))

        def one(task, repeat):
            base, request = position(root, checkpoint, benchmark, task, repeat)
            if (base / "prediction.json").exists():
                record = read_json(base / "prediction.json", sealed=True)
                require(record["request"] == request, "Prediction belongs to another task/checkpoint")
                return record
            write_json(base / "intent.json", seal(request))
            position_runtime = {**runtime, "work_dir": str(base / "workspace")}
            max_calls = runtime.get("max_steps", 50) if benchmark == "alfworld" else 1
            require(type(max_calls) is int and 1 <= max_calls <= 150, "Invalid turn budget")
            call = fixture_call if is_fixture else PositionCalls(api, base, request, model["max_tokens"], max_calls)
            # This is the ONLY model/backend solve view: no task ID, label,
            # answer, hidden test, family, method, history or checkpoint metadata.
            solve = fixture_solve if is_fixture else backends.solve
            prediction = _valid_prediction(solve(benchmark, public_view(task), checkpoint["skill_text"], call,
                                                 runtime=position_runtime))
            record = seal({"request": request, "prediction": prediction,
                           "evidence_kind": plan["evidence_kind"], "costs": _position_costs(base),
                           "score_feedback_allowed": False})
            write_json(base / "prediction.json", record)
            return record

        try:
            # Do not reserve an entire panel while the provider health barrier
            # is unresolved. Backends return typed unknowns for call failures;
            # the orchestrator must still stop a failed initial connection.
            if api is not None:
                # On resume, a cached first slot says nothing about this new
                # client's health. Probe the first unperformed position without
                # resampling any previous success or terminal unknown.
                first_pending = pending[0]
                one(*first_pending)
                first_calls = _stored_calls(position(root, checkpoint, benchmark, *first_pending)[0])
                require(first_calls and any(api._initial_ready(r) for r in first_calls),
                        "Initial API health check failed; remaining positions were not submitted")
            if workers == 1:
                records = [one(*slot) for slot in slots]
            else:
                with ThreadPoolExecutor(max_workers=workers) as pool:
                    records = list(pool.map(lambda pair: one(*pair), slots))
        finally:
            if api is not None:
                api.close()
        return {"positions": len(records), "available": sum(r["prediction"]["status"] == "available" for r in records),
                "unknown": sum(r["prediction"]["status"] == "unknown" for r in records),
                "new_positions": len(pending), "scores_read": False, "evidence_kind": plan["evidence_kind"]}


def close_interrupted(root, key):
    """Explicitly retain an uncertain interrupted attempt; never sample again."""
    require(type(key) is str and len(key) == 64 and all(c in "0123456789abcdef" for c in key), "Invalid position key")
    root = safe_path(root)
    with output_lock(root):
        load_plan(root)
        base = root / "predictions" / key
        intent = read_json(base / "intent.json", sealed=True)
        request = {k: v for k, v in intent.items() if k != "record_hash"}
        require(digest(request) == key, "Interrupted position identity mismatch")
        require(not (base / "prediction.json").exists(), "Position is already terminal")
        record = seal({"request": request, "prediction": {"status": "unknown", "output": "",
            "reason": "operator_closed_interrupted_attempt"}, "costs": _position_costs(base),
            "evidence_kind": "interrupted_attempt", "score_feedback_allowed": False,
            "unclosed_call_count": len(list((base / "call_intents").glob("*.json"))) - len(_stored_calls(base))})
        write_json(base / "prediction.json", record)
        return {"position": key, "status": "unknown", "resampled": False}


def _valid_score(result):
    require(type(result) is dict and result.get("status") in {"pass", "fail", "unknown"}, "Invalid native score status")
    require(set(result) <= {"status", "score", "metrics", "reason", "runtime_image_id", "cleanup_confirmed",
                            "runtime_architecture", "execution_costs"},
            "Unexpected scorer fields cannot override host identity")
    score = result.get("score")
    if result["status"] == "unknown":
        require(score is None, "Unknown must not become a semantic zero")
    else:
        require(type(score) in {int, float} and 0 <= score <= 1, "Native primary score must be in [0,1]")
    require(type(result.get("reason")) is str and type(result.get("metrics")) is dict, "Missing native score evidence")
    return result


def score_checkpoint(root, *, method, history, stage, benchmark, fixture_score=None):
    from . import backends

    root = safe_path(root)
    with output_lock(root):
        plan = load_plan(root)
        checkpoint = load_checkpoint(root, method, history, stage, plan)
        tasks = panel_tasks(plan, benchmark)
        is_fixture = plan["config"]["model"]["provider"] == "fixture"
        require(is_fixture == (fixture_score is not None), "Fixture scoring is restricted to fixture plans")
        runtime = dict(plan["config"]["runtime"].get(benchmark, {}))
        score_fn = fixture_score if is_fixture else backends.score
        completed, missing = 0, 0
        for task in tasks:
            for repeat in range(plan["repeats"]):
                base, request = position(root, checkpoint, benchmark, task, repeat)
                if not (base / "prediction.json").exists():
                    missing += 1
                    continue
                prediction = read_json(base / "prediction.json", sealed=True)
                require(prediction["request"] == request, "Prediction binding mismatch")
                value = prediction["prediction"]
                score_runtime = {**runtime, "work_dir": str(base / "workspace")}
                recalc_profile = benchmark == "spreadsheetbench" and runtime.get("spreadsheet_scorer") in {
                    "qualified_lo_recalc_v5_v1", "qualified_lo_recalc_v7_v1"}
                if recalc_profile:
                    score_runtime["_score_context"] = {
                        "artifact_dir": str(root / "host_only/scorer_artifacts" / base.name),
                        "position": base.name, "request": request, "prediction_hash": prediction["record_hash"]}
                target = root / "host_only" / "scores" / (base.name + ".json")
                if target.exists():
                    prior = read_json(target, sealed=True)
                    require(prior["prediction_hash"] == prediction["record_hash"], "Score cache binding mismatch")
                    if recalc_profile and value["status"] == "available":
                        if runtime["spreadsheet_scorer"] == "qualified_lo_recalc_v7_v1":
                            from .sheet_numeric_adapter import score as recalc_score
                        else:
                            from .sheet_recalc_adapter import score as recalc_score

                        replay = recalc_score(public_view(task), task["private"], value,
                                             runtime=score_runtime, replay_only=True)
                        require(all(prior[key] == val for key, val in replay.items()), "Cached recalculation score differs")
                    completed += 1
                    continue
                intent = root / "host_only" / "score_intents" / (base.name + ".json")
                require(not intent.exists(), "Interrupted native score; preserve it and review before recovery")
                write_json(intent, seal({"request": request, "prediction_hash": prediction["record_hash"]}))
                if value["status"] == "unknown":
                    result = {"status": "unknown", "score": None, "metrics": {}, "reason": value["reason"]}
                else:
                    result = score_fn(benchmark, public_view(task), task["private"], value,
                                      runtime=score_runtime)
                result = _valid_score(result)
                row = seal({"plan_hash": plan["record_hash"], "checkpoint_hash": checkpoint["record_hash"],
                    "method": method, "history": history, "stage": stage, "benchmark": benchmark,
                    "task_id": task["task_id"], "family_id": task["family_id"], "repeat": repeat,
                    "prediction_hash": prediction["record_hash"], "costs": prediction["costs"],
                    "evidence_kind": plan["evidence_kind"], **result})
                write_json(target, row)
                completed += 1
        return {"completed": completed, "missing_predictions": missing, "model_calls": 0,
                "score_feedback_allowed": False}


def report(root):
    from .metrics import summarize

    root = safe_path(root)
    plan = load_plan(root)
    # Dynamic publication state is separate from the immutable roster/plan.
    registered = {}
    for slot in plan["checkpoints"]:
        path = checkpoint_path(root, slot["method"], slot["history"], slot["stage"])
        if path.exists():
            cp = load_checkpoint(root, slot["method"], slot["history"], slot["stage"], plan)
            registered[cp["record_hash"]] = cp
    rows = []
    for path in sorted((root / "host_only" / "scores").glob("*.json")):
        row = read_json(path, sealed=True)
        require(row["plan_hash"] == plan["record_hash"] and row["checkpoint_hash"] in registered,
                "Unregistered score/checkpoint")
        cp = registered[row["checkpoint_hash"]]
        require(all(row[k] == cp[k] for k in ("method", "history", "stage")), "Score checkpoint identity mismatch")
        prediction = read_json(root / "predictions" / path.stem / "prediction.json", sealed=True)
        require(prediction["record_hash"] == row["prediction_hash"], "Scored prediction changed")
        task = next((t for t in plan["tasks"] if t["benchmark"] == row["benchmark"]
                     and t["task_id"] == row["task_id"]), None)
        require(task is not None and task["family_id"] == row["family_id"], "Score task identity mismatch")
        expected = {"plan_hash": plan["record_hash"], "checkpoint_hash": cp["record_hash"],
                    "benchmark": row["benchmark"], "task_hash": task["task_hash"], "repeat": row["repeat"]}
        require(prediction["request"] == expected and path.stem == digest(expected),
                "Score task/repeat differs from prediction identity")
        rows.append(row)
    metric_plan = deepcopy(plan)
    for slot in metric_plan["checkpoints"]:
        for cp in registered.values():
            if all(slot[k] == cp[k] for k in ("method", "history", "stage")):
                slot["checkpoint_hash"] = cp["record_hash"]
    value = summarize(metric_plan, rows)
    position_dirs = sorted(p for p in (root / "predictions").glob("*") if p.is_dir())
    all_receipts = [r for base in position_dirs for r in _stored_calls(base)]
    unclosed = sum(len(list((base / "call_intents").glob("*.json"))) - len(_stored_calls(base))
                   for base in position_dirs)
    result = seal({"version": "continual-eval-report-v1", "plan_hash": plan["record_hash"],
                   "evidence_kind": plan["evidence_kind"], "protocol_complete": plan["protocol_complete"],
                   "score_feedback_allowed": False, "deployment_authorized": False, "summary": value,
                   "run_accounting": {**_costs(all_receipts, unclosed=unclosed),
                       "scope": "all_positions_including_unscored_and_interrupted",
                       "reserved_positions": len(position_dirs),
                       "terminal_predictions": sum((base / "prediction.json").is_file() for base in position_dirs),
                       "scored_positions": len(rows)}, "summary_cost_scope": "scored_positions_only"})
    write_json(root / "host_only" / "reports" / (result["record_hash"] + ".json"), result)
    return result
