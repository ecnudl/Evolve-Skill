"""Pinned native GEPA, authorized development stages; no implicit resume."""
from __future__ import annotations

import hashlib
import importlib
import json
import subprocess
from pathlib import Path

from skillopt.coevolution_v5.core import seal
from skillopt.continual_eval import backends
from skillopt.continual_eval.core import output_lock, read_json, require, safe_path, write_json
from skillopt.continual_eval.runner import _valid_prediction, _valid_score
from skillopt.validator_pilot.api import CachedAPI, digest

from . import GEPA_COMMIT
from .contracts import DELIVERY_VERSIONS, HARDENED_VERSION, MULTIDOMAIN_VERSIONS, check_skill, validate_manifest
from .feedback import artifacts, benchmark_for, project, verify_task_assets
from .ledger import BudgetExhausted, LearningPending, Ledger
from .recovery import client_options, solver_call


def official_gepa(source):
    """Require an installed package byte-identical to the reviewed official source."""
    source = safe_path(source)
    commit = subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip()
    require(commit == GEPA_COMMIT, "GEPA commit differs from the reviewed pin")
    dirty = subprocess.check_output(
        ["git", "-C", str(source), "status", "--porcelain", "--untracked-files=all", "--", "src/gepa"], text=True)
    require(not dirty, "Reviewed GEPA sources were modified")
    spec = importlib.util.find_spec("gepa")
    require(spec is not None and spec.origin is not None, "Install the pinned GEPA in an isolated environment first")
    installed = Path(spec.origin).parent
    reference = source / "src/gepa"
    names = {p.relative_to(reference) for p in reference.rglob("*.py")}
    require(names == {p.relative_to(installed) for p in installed.rglob("*.py")}, "GEPA source roster differs")
    require(all((reference / name).read_bytes() == (installed / name).read_bytes() for name in names),
            "Installed GEPA differs from pinned official source")
    module = importlib.import_module("gepa")
    return module, {str(n): hashlib.sha256((reference / n).read_bytes()).hexdigest() for n in sorted(names)}


class _QuietLogger:
    def log(self, message):
        pass


def _cleanup_unconfirmed(value):
    """Inspect host execution metadata; a flagged cleanup is not a score."""
    if isinstance(value, dict):
        return any((key in {"cleanup_confirmed", "cleaned_up"} and item is False)
                   or (key in {"reason", "status", "error_type"} and isinstance(item, str)
                       and "cleanup_unconfirmed" in item)
                   or _cleanup_unconfirmed(item) for key, item in value.items())
    return isinstance(value, list) and any(_cleanup_unconfirmed(item) for item in value)


class Adapter:
    propose_new_texts = None  # Keep the official reflective proposer, not our own optimizer.

    def __init__(self, manifest, root, ledger, *, fixture_evaluate=None):
        self.manifest, self.root, self.ledger = manifest, root, ledger
        self.fixture_evaluate = fixture_evaluate
        self.calls = 0
        self.pending_reason = None

    def _pending(self, reason, *, budget=False):
        self.pending_reason = reason
        raise (BudgetExhausted if budget else LearningPending)(reason)

    def _guard_cleanup(self, row, key):
        if self.manifest["version"] != HARDENED_VERSION:
            return
        if _cleanup_unconfirmed(row):
            self._pending("native_cleanup_unconfirmed")
        # A scorer may fail to project a lower-level receipt into its result.
        # Check only this position's host-owned artifacts, never another run.
        for path in sorted((self.root / "host_only/scorer_artifacts" / key).rglob("*.json")):
            try:
                evidence = read_json(path)
            except (OSError, ValueError, TypeError):
                self._pending("native_cleanup_evidence_unreadable")
            if _cleanup_unconfirmed(evidence):
                self._pending("native_cleanup_unconfirmed")

    def _score_runtime(self, request, key, prediction):
        runtime = self.manifest["runtime"]
        if self.manifest["version"] in MULTIDOMAIN_VERSIONS:
            runtime = {**runtime, "work_dir": str(self.root / "host_only/workspaces" / key)}
        if (benchmark_for(self.manifest) == "spreadsheetbench"
                and runtime.get("spreadsheet_scorer") in {"qualified_lo_recalc_v5_v1", "qualified_lo_recalc_v7_v1"}):
            root = self.root / "host_only/scorer_artifacts" / key
            record = seal({"request": request, "prediction": prediction})
            write_json(root / "prediction.json", record)
            return {**runtime, "_score_context": {
                "artifact_dir": str(root), "position": key, "request": request,
                "prediction_hash": record["record_hash"]}}
        return runtime

    def evaluate_rows(self, batch, candidate, *, rollout=None):
        """Shared execution records, with no GEPA dependency for other learners."""
        if self.pending_reason:
            raise LearningPending(self.pending_reason)
        require(set(candidate) == {"skill"}, "Only the Skill component is optimizable")
        try:
            check_skill(candidate["skill"])
        except ValueError as exc:
            self.pending_reason = "invalid_candidate_skill_length"
            raise LearningPending(self.pending_reason) from exc
        outputs, scores, trajectories = [], [], []
        benchmark = benchmark_for(self.manifest)
        multidomain = self.manifest["version"] in MULTIDOMAIN_VERSIONS
        for item in batch:
            task = item["task"]
            require(task.get("partition") == "development"
                    and self.manifest["authorized_tasks"].get(digest(task)) == item["role"],
                    "Task or role is not authorized by the frozen development manifest")
            verify_task_assets(self.manifest, task)
            request = {"manifest_hash": self.manifest["record_hash"], "candidate_hash": digest(candidate),
                       "task_hash": digest(task), "role": item["role"], "repeat": 0}
            if multidomain:
                request["benchmark"] = benchmark
            if rollout is not None:
                # V5 only: every native update gets a fresh train rollout.
                require(self.manifest["version"] in DELIVERY_VERSIONS and item["role"] == "train"
                        and type(rollout) is int and rollout >= 0, "Rollout keys are v5 train-only")
                request["rollout"] = rollout
            key = digest(request)
            path = self.root / "evaluations" / (key + ".json")
            ledger_stops = []
            if path.exists():
                row = read_json(path, sealed=True)
                require(row["request"] == request, "Evaluation cache identity differs")
                require(read_json(self.root / "evaluation_intents" / (key + ".json"), sealed=True) == seal(request),
                        "Evaluation cache has no matching intent")
                self._guard_cleanup(row, key)
                if (not self.fixture_evaluate and row["prediction"]["status"] == "available"
                        and benchmark == "spreadsheetbench"
                        and self.manifest["runtime"].get("spreadsheet_scorer") in {
                            "qualified_lo_recalc_v5_v1", "qualified_lo_recalc_v7_v1"}):
                    if self.manifest["runtime"]["spreadsheet_scorer"] == "qualified_lo_recalc_v7_v1":
                        from skillopt.continual_eval.sheet_numeric_adapter import score as recalc_score
                    else:
                        from skillopt.continual_eval.sheet_recalc_adapter import score as recalc_score

                    replay = recalc_score(task["public"], task["private"], row["prediction"],
                                         runtime=self._score_runtime(request, key, row["prediction"]), replay_only=True)
                    require(replay == row["score"], "Cached learning recalculation evidence changed")
            else:
                intent_path = self.root / "evaluation_intents" / (key + ".json")
                if intent_path.exists():
                    self._pending("interrupted_evaluation")
                if len(list((self.root / "evaluation_intents").glob("*.json"))) >= self.manifest["budget"]["max_metric_calls"]:
                    self._pending("max_metric_calls", budget=True)
                write_json(intent_path, seal(request))
                if self.fixture_evaluate:
                    prediction, score = self.fixture_evaluate(task, candidate["skill"])
                else:
                    turn = 0

                    def call(system, user):
                        nonlocal turn
                        logical_id = f"{key}:turn:{turn}" if multidomain else key
                        turn += 1
                        try:
                            return solver_call(self.ledger, logical_id, system, user)
                        except LearningPending as exc:
                            # The solver adapter records this position as unknown;
                            # keep the actual ledger/budget stop for the stage reason.
                            ledger_stops.append(exc)
                            raise

                    runtime = self.manifest["runtime"]
                    if multidomain:
                        runtime = {**runtime, "work_dir": str(self.root / "host_only/workspaces" / key)}
                    if self.manifest["version"] == HARDENED_VERSION:
                        runtime = {**runtime, "_stop_on_cleanup_failure": True}
                    prediction = backends.solve(benchmark, task["public"], candidate["skill"], call,
                                                runtime=runtime)
                    prediction = _valid_prediction(prediction)
                    if self.manifest["version"] == HARDENED_VERSION and _cleanup_unconfirmed(prediction):
                        # Persist the prediction/unknown before stopping, but do
                        # not launch a scorer after solver cleanup has failed.
                        score = {"status": "unknown", "score": None, "metrics": {},
                                 "reason": "native_cleanup_unconfirmed"}
                    else:
                        score = backends.score(benchmark, task["public"], task["private"], prediction,
                                               runtime=self._score_runtime(request, key, prediction))
                row = seal({"request": request, "prediction": _valid_prediction(prediction),
                            "score": _valid_score(score)})
                write_json(path, row)
            self._guard_cleanup(row, key)
            if row["score"]["status"] == "unknown":
                if ledger_stops and self.manifest["version"] in DELIVERY_VERSIONS:
                    self._pending(str(ledger_stops[0]), budget=isinstance(ledger_stops[0], BudgetExhausted))
                if self.manifest["version"] not in DELIVERY_VERSIONS:
                    self._pending("evaluation_unknown")
                # V5: an unknown score is neither feedback nor zero; the learner
                # excludes it from reflection and from the paired selection.
                outputs.append({"output": None, "evidence_hash": row["record_hash"]})
                trajectories.append(None)
                scores.append(None)
                continue
            # Deliberately no private tests, hidden traceback or full metrics in reflection.
            try:
                trace = project(self.manifest, task["public"], row["prediction"], row["score"])
            except (ValueError, KeyError, TypeError) as exc:
                if multidomain:
                    self.pending_reason = "public_feedback_projection_unavailable"
                    raise LearningPending(self.pending_reason) from exc
                raise
            outputs.append({"output": trace["Generated Outputs"], "evidence_hash": row["record_hash"]})
            trajectories.append(trace)
            scores.append(row["score"]["score"])
        self.calls += len(batch)
        return [{"output": out, "score": score, "trajectory": trace}
                for out, score, trace in zip(outputs, scores, trajectories)]

    def evaluate(self, batch, candidate, capture_traces=False):
        from gepa.core.adapter import EvaluationBatch
        rows = self.evaluate_rows(batch, candidate)
        outputs = [r["output"] for r in rows]
        scores = [r["score"] for r in rows]
        trajectories = [r["trajectory"] for r in rows]
        return EvaluationBatch(outputs=outputs, scores=scores, trajectories=trajectories if capture_traces else None)

    def make_reflective_dataset(self, candidate, eval_batch, components_to_update):
        require(components_to_update == ["skill"], "Unexpected optimizable component")
        return {"skill": eval_batch.trajectories}


def run_stage(manifest, panel, output, *, gepa_source, repo=None, fixture_api=None, fixture_evaluate=None):
    """Complete replay is supported. Incomplete runs remain Pending, never restarted."""
    validate_manifest(manifest, panel)
    require(manifest["method"] == "gepa", "GEPA cannot run another method's learning manifest")
    fixture = manifest["model"]["provider"] == "fixture"
    require(fixture == (fixture_api is not None and fixture_evaluate is not None), "Fixture callbacks required only for fixture")
    require(fixture or (fixture_api is None and fixture_evaluate is None), "Natural run cannot inject fixture callbacks")
    official, source_hashes = official_gepa(gepa_source)
    root = safe_path(output)
    with output_lock(root):
        identity = seal({"manifest": manifest, "official_sources": source_hashes})
        write_json(root / "identity.json", identity)
        write_json(root / "panel.json", panel)
        terminal = root / "result.json"
        if terminal.exists():
            result = read_json(terminal, sealed=True)
            check = Ledger(root, manifest, None)
            require(result["identity_hash"] == identity["record_hash"] and result["artifacts"] == artifacts(check),
                    "Completed learning evidence changed")
            check.snapshot()
            return result
        if (root / "started.json").exists():
            return {"status": "pending", "reason": "interrupted_stage_no_automatic_optimizer_resume",
                    "deployment_authorized": False, "model_calls_submitted": 0,
                    "costs": Ledger(root, manifest, None).snapshot()}
        if not fixture:
            require(repo is not None, "Natural run needs credential repository")
            ready = backends.readiness(benchmark_for(manifest), manifest["runtime"])
            require(ready["status"] == "ready", "Benchmark native runtime is not ready")
        write_json(root / "started.json", seal({"identity_hash": identity["record_hash"]}))
        api = fixture_api
        try:
            if not fixture:
                model = manifest["model"]
                api = CachedAPI(Path(repo), root / "api", provider=model["provider"], model=model["name"],
                                workers=1, reasoning_effort=model["reasoning_effort"],
                                **model.get("transport", {"initial_health_policy": "completed_response_v1"}),
                                **client_options(manifest),
                                **({"proxy": model["proxy"]} if "proxy" in model else {}))
            write_json(root / "model_service.json", seal(api.service))
            ledger = Ledger(root, manifest, api)
            adapter = Adapter(manifest, root, ledger, fixture_evaluate=fixture_evaluate)
            reflection_index = 0
            reflection_pending = []

            def reflection(prompt):
                nonlocal reflection_index
                if reflection_pending:
                    raise LearningPending(reflection_pending[0])
                require(type(prompt) is str, "Only official single-string reflection prompts are supported")
                index = reflection_index
                reflection_index += 1
                try:
                    receipt = ledger.call("reflection", str(index),
                        "Optimize only the Skill text. Keep it within 6000 UTF-8 bytes; preserve the requested output fences.",
                        prompt, manifest["budget"]["reflection_max_tokens"])
                except Exception as exc:
                    reflection_pending.append(str(exc) if isinstance(exc, LearningPending) else type(exc).__name__)
                    adapter.pending_reason = reflection_pending[0]
                    raise
                if not receipt.get("ok") or receipt.get("finish_reason") != "stop":
                    reflection_pending.append("reflection_unavailable")
                    adapter.pending_reason = reflection_pending[0]
                    raise LearningPending("reflection_unavailable")
                return receipt["response"]

            train, selection = [], []
            for task in panel["tasks"]:
                role = "train" if task["family_id"] in manifest["train_families"] else "selection"
                (train if role == "train" else selection).append({"role": role, "task": task})
            budget = manifest["budget"]
            result = official.optimize(
                seed_candidate={"skill": manifest["parent_skill"]}, trainset=train, valset=selection,
                adapter=adapter, reflection_lm=reflection, candidate_selection_strategy="pareto",
                frontier_type="instance", reflection_minibatch_size=budget["minibatch_size"],
                use_merge=False, max_metric_calls=budget["max_metric_calls"],
                stop_callbacks=lambda state: state.i + 1 >= budget["max_iterations"],
                seed=manifest["seed"], raise_on_exception=True, cache_evaluation=True,
                logger=_QuietLogger(), run_dir=str(root / "official_state"), use_cloudpickle=False)
            # Native GEPA can catch proposer exceptions and skip a mutation.
            # That is not evidence that an unavailable paid request succeeded.
            if reflection_pending or adapter.pending_reason:
                raise LearningPending((reflection_pending or [adapter.pending_reason])[0])
            skill = check_skill(result.best_candidate["skill"])
            result_payload = {"status": "completed", "candidate_skill": skill,
                              "official_result": json.loads(json.dumps(result.to_dict(), allow_nan=False)),
                              "reason": "official_gepa_development_selection"}
        except Exception as exc:
            # Preserve partial evidence; never label API/runtime failures as model failures.
            result_payload = {"status": "pending", "candidate_skill": manifest["parent_skill"],
                              "reason": str(exc) if isinstance(exc, LearningPending) else type(exc).__name__}
        finally:
            if api is not None and not fixture:
                api.close()
        ledger = Ledger(root, manifest, api)
        costs = ledger.snapshot()
        if ledger.usage_blocks_completion(costs) and result_payload["status"] == "completed":
            result_payload.update(status="pending", candidate_skill=manifest["parent_skill"], reason="incomplete_usage")
        record = seal({"version": manifest["version"], "identity_hash": identity["record_hash"], **result_payload,
                       "evidence_kind": manifest["evidence_kind"], "costs": costs, "artifacts": artifacts(ledger),
                       "deployment_authorized": False, "scope_expansion_authorized": False,
                       "resume_supported": False})
        write_json(terminal, record)
        return record
