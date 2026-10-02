"""Bounded native SkillOpt patch proposal for explicitly authorized development.

Reuse the repository's real reflection/merge/ranking/application code, not a
replacement optimizer prompt. This module does not authorize deployment.
"""
from __future__ import annotations

import hashlib
import math
import threading
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path

from skillopt.coevolution_v5.core import seal
from skillopt.continual_eval.core import output_lock, read_json, require, safe_path, write_json
from skillopt.validator_pilot.api import CachedAPI, digest

from .contracts import check_skill, validate_manifest
from .feedback import artifacts, benchmark_for, project, task_description, validate_public
from .ledger import LearningPending, Ledger
from .recovery import VERSION as RECOVERY_VERSION
from .recovery import client_options
from .reflection_json import POLICY as PARSER_POLICY
from .reflection_json import NativeJSONError, prepare_native_json, strict_native_object

_NATIVE_LOCK = threading.RLock()


def native_sources():
    root = Path(__file__).resolve().parents[1]
    names = ["engine/trainer.py", "gradient/reflect.py", "gradient/aggregate.py",
             "optimizer/clip.py", "optimizer/skill.py", "optimizer/update_modes.py",
             "optimizer/meta_skill.py", "optimizer/skill_aware.py", "evaluation/gate.py",
             "utils/json_utils.py", "prompts/analyst_error.md", "prompts/analyst_success.md",
             "prompts/merge_failure.md", "prompts/merge_success.md", "prompts/merge_final.md",
             "prompts/ranking.md"]
    return {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in names}


class _NativeBridge:
    def __init__(self, ledger, step, *, audit_root=None):
        self.ledger, self.step = ledger, step
        self.calls = 0
        self.failure = None
        self.strict_parser = ledger.manifest["version"] == RECOVERY_VERSION
        self.audit_root = safe_path(audit_root) if audit_root is not None else None
        if self.strict_parser:
            require(ledger.manifest.get("recovery_policy", {}).get("reflection_parser") == PARSER_POLICY,
                    "Native parser recovery policy differs")
            require(self.audit_root is not None, "Native parser audit output required")

    def chat(self, system, user, max_completion_tokens=16384, retries=3, stage="optimizer", **kwargs):
        if self.failure is not None:
            raise LearningPending("earlier_native_optimizer_failure")
        try:
            require(stage in {"analyst", "merge", "ranking"} and not kwargs,
                    "Unsupported native optimizer transport options")
            require(type(max_completion_tokens) is int and max_completion_tokens > 0,
                    "Invalid native optimizer token budget")
            cap = min(max_completion_tokens, self.ledger.manifest["budget"]["reflection_max_tokens"])
            index = self.calls
            self.calls += 1
            receipt = self.ledger.call("reflection", f"skillopt:{self.step}:{stage}:{index}",
                                       system, user, cap)
            if not receipt.get("ok") or receipt.get("finish_reason") != "stop":
                raise LearningPending("native_optimizer_response_unknown")
            require(type(receipt.get("response")) is str, "Missing optimizer response")
            response = receipt["response"]
            if self.strict_parser:
                binding = {"manifest_hash": self.ledger.manifest["record_hash"], "step": self.step,
                           "stage": stage, "call_index": index, "receipt_hash": digest(receipt),
                           "request_hash": receipt["request_hash"],
                           "call_intent_hash": receipt["request"]["key"]}
                try:
                    response, audit = prepare_native_json(response)
                except NativeJSONError as exc:
                    write_json(self.audit_root / f"{index}.json", seal({**binding, **exc.audit}))
                    raise LearningPending("native_optimizer_json_rejected:" + exc.reason) from exc
                write_json(self.audit_root / f"{index}.json", seal({**binding, **audit}))
            return response, deepcopy(receipt.get("usage", {}))
        except Exception as exc:
            # Upstream has fallbacks that catch exceptions; do not let a
            # transport failure become an apparently complete learned candidate.
            self.failure = exc
            raise


@contextmanager
def _transport(bridge):
    from skillopt.gradient import aggregate, reflect
    from skillopt.optimizer import clip

    with _NATIVE_LOCK:
        modules = (reflect, aggregate, clip)
        originals = [module.chat_optimizer for module in modules]
        parsers = [module.extract_json for module in modules]
        try:
            for module in modules:
                module.chat_optimizer = bridge.chat
                if bridge.strict_parser:
                    module.extract_json = strict_native_object
            yield
        finally:
            for module, original, parser in zip(modules, originals, parsers):
                module.chat_optimizer = original
                if bridge.strict_parser:
                    module.extract_json = parser


def _validate_traces(traces, benchmark="bigcodebench"):
    require(type(traces) is list and traces, "Nonempty authorized development traces required")
    for trace in traces:
        require(type(trace) is dict and set(trace) == {"Inputs", "Generated Outputs", "Feedback", "evidence_hash"},
                "Only explicitly projected feedback fields are allowed")
        public, feedback = trace["Inputs"], trace["Feedback"]
        validate_public(benchmark, public)
        require(type(trace["Generated Outputs"]) is str, "Actual output required")
        require(type(feedback) is dict and set(feedback) == {"status", "score"}, "Only scalar native feedback allowed")
        if feedback["status"] == "unknown":
            raise LearningPending("unknown_is_not_failure_feedback")
        require(feedback["status"] in {"pass", "fail"}
                and feedback["score"] == int(feedback["status"] == "pass"), "Inconsistent native hard feedback")
        token = trace["evidence_hash"]
        require(type(token) is str and len(token) == 64 and all(c in "0123456789abcdef" for c in token),
                "Bound execution evidence required")
    require(len({t["evidence_hash"] for t in traces}) == len(traces), "Duplicate development evidence")


def _bind_traces(traces, ledger, parent_skill):
    """Resolve projections to this learner's actual authorized train evidence."""
    panel = read_json(ledger.root / "panel.json")
    require(digest(panel) == ledger.manifest["panel_hash"], "Feedback panel is not authorized")
    tasks = {digest(task): task for task in panel["tasks"]}
    evidence = {}
    for path in sorted((ledger.root / "evaluations").glob("*.json")):
        row = read_json(path, sealed=True)
        evidence[row["record_hash"]] = (path, row)
    for trace in traces:
        require(trace["evidence_hash"] in evidence, "Feedback has no current learning execution evidence")
        path, row = evidence[trace["evidence_hash"]]
        request = row["request"]
        task = tasks.get(request["task_hash"])
        require(task is not None and request["manifest_hash"] == ledger.manifest["record_hash"]
                and request["role"] == "train" and task["partition"] == "development"
                and ledger.manifest["authorized_tasks"].get(request["task_hash"]) == "train"
                and request["candidate_hash"] == digest({"skill": parent_skill}),
                "Feedback role, task, parent or authorization mismatch")
        require(read_json(ledger.root / "evaluation_intents" / path.name, sealed=True) == seal(request),
                "Feedback execution intent mismatch")
        expected = project(ledger.manifest, task["public"], row["prediction"], row["score"])
        require({key: trace[key] for key in expected} == expected,
                "Feedback projection differs from actual execution")


def propose_native(parent_skill, traces, output, ledger, *, step=0, seed=0, minibatch_size=8, edit_budget=4):
    """One real reflect -> aggregate -> clip -> patch pass; no selection gate.

    ``traces`` must come from the new learner's authorized execution adapter,
    never from reinterpreting a frozen no-feedback evaluation artifact.
    """
    from skillopt.engine.trainer import _normalise_patches
    from skillopt.gradient import aggregate, reflect
    from skillopt.optimizer import clip
    from skillopt.optimizer.skill import apply_patch_with_report

    check_skill(parent_skill)
    benchmark = benchmark_for(ledger.manifest)
    _validate_traces(traces, benchmark)
    require(ledger.manifest.get("method") == "skillopt", "SkillOpt learning authorization required")
    _bind_traces(traces, ledger, parent_skill)
    require(type(step) is int and step >= 0 and type(seed) is int and seed >= 0, "Invalid step or seed")
    require(type(minibatch_size) is int and 1 <= minibatch_size <= 64, "Invalid native minibatch size")
    require(type(edit_budget) is int and 1 <= edit_budget <= 16, "Invalid native edit budget")
    root = safe_path(output)
    identity = seal({"parent_skill": parent_skill, "traces_hash": digest(traces),
                     "manifest_hash": ledger.manifest["record_hash"], "native_sources": native_sources(),
                     "step": step, "seed": seed, "minibatch_size": minibatch_size,
                     "edit_budget": edit_budget, "meta": False, "slow": False, "skill_aware": False,
                     "native_generic_prompts": True, "acceptance": "external_development_selection"})
    write_json(root / "identity.json", identity)
    if (root / "result.json").exists():
        result = read_json(root / "result.json", sealed=True)
        require(result["identity_hash"] == identity["record_hash"], "Native proposal identity differs")
        return result
    if (root / "started.json").exists():
        raise LearningPending("native_proposal_interrupted_no_automatic_resume")
    write_json(root / "started.json", seal({"identity_hash": identity["record_hash"]}))
    native_rows = []
    for trace in traces:
        token = trace["evidence_hash"]
        description = task_description(benchmark, trace["Inputs"])
        write_json(root / "predictions" / token / "conversation.json", [
            {"role": "user", "content": description},
            {"role": "assistant", "content": trace["Generated Outputs"]},
            {"role": "system", "content": "Development native checker: " + trace["Feedback"]["status"]
             + ". Hidden tests and expected answers are not provided."},
        ])
        native_rows.append({"id": token, "hard": trace["Feedback"]["score"], "n_turns": 1,
                            "task_description": description, "task_type": "coding" if benchmark == "bigcodebench" else benchmark,
                            "fail_reason": ("Native development tests failed" if benchmark == "bigcodebench"
                                            else "Native development check failed")
                            if trace["Feedback"]["status"] == "fail" else ""})
    bridge = _NativeBridge(ledger, step, audit_root=root / "parser_audits")
    with _transport(bridge):
        raw = sorted(reflect.run_minibatch_reflect(
            native_rows, parent_skill, str(root / "predictions"), str(root / "patches"),
            workers=1, failure_only=False, minibatch_size=minibatch_size, edit_budget=edit_budget,
            random_seed=seed, error_system=None, success_system=None, update_mode="patch",
            step_buffer_context="", meta_skill_context="", skill_aware_reflection=False), key=digest)
        if bridge.failure is not None:
            raise LearningPending("native_reflection_incomplete") from bridge.failure
        expected = sum(math.ceil(sum(row["hard"] == value for row in native_rows) / minibatch_size)
                       for value in (0, 1))
        if len(raw) != expected:
            raise LearningPending("native_reflection_parse_incomplete")
        failure, success = _normalise_patches(deepcopy(raw), update_mode="patch")
        merged = aggregate.merge_patches(parent_skill, failure, success, batch_size=8,
                                         workers=1, verbose=False, update_mode="patch")
        selected = clip.rank_and_select(parent_skill, merged, max_edits=edit_budget, update_mode="patch")
    if bridge.failure is not None:
        raise LearningPending("native_optimizer_incomplete") from bridge.failure
    candidate, application = apply_patch_with_report(parent_skill, selected)
    try:
        check_skill(candidate)
    except ValueError as exc:
        raise LearningPending("native_candidate_exceeds_skill_budget") from exc
    result = seal({"identity_hash": identity["record_hash"], "candidate_skill": candidate,
                   "status": "candidate_ready" if candidate != parent_skill else "no_update",
                   "raw": raw, "merged": merged, "selected": selected, "application": application,
                   "optimizer_calls": bridge.calls, "deployment_authorized": False})
    write_json(root / "result.json", result)
    return result


def _stage_artifacts(root, ledger):
    return {**artifacts(ledger), **{
        str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
        for folder in ("native", "steps") for p in sorted((root / folder).rglob("*.json"))}}


def run_stage(manifest, panel, output, *, repo=None, fixture_api=None, fixture_evaluate=None):
    """Native source-only gate; repeated stages inherit the caller's parent Skill.

    Fixed full train passes and source selection; no meta/slow update, adaptive
    learning rate, history replay, routing or independent final evaluation.
    """
    from skillopt.continual_eval import backends
    from skillopt.evaluation.gate import evaluate_gate

    from .gepa import Adapter  # evaluate_rows itself has no GEPA dependency.

    validate_manifest(manifest, panel)
    require(manifest["method"] == "skillopt", "SkillOpt cannot run another method's manifest")
    fixture = manifest["model"]["provider"] == "fixture"
    require(fixture == (fixture_api is not None and fixture_evaluate is not None), "Invalid fixture callbacks")
    require(fixture or (fixture_api is None and fixture_evaluate is None), "Natural run cannot inject fixtures")
    root = safe_path(output)
    with output_lock(root):
        identity = seal({"manifest": manifest, "native_sources": native_sources(),
                         "edit_budget": 4, "gate": "native_hard_strict_improvement",
                         "training_schedule": "full_train_pass_per_update",
                         "meta": False, "slow": False, "skill_aware": False})
        write_json(root / "identity.json", identity)
        write_json(root / "panel.json", panel)
        terminal = root / "result.json"
        if terminal.exists():
            result = read_json(terminal, sealed=True)
            ledger = Ledger(root, manifest, None)
            require(result["identity_hash"] == identity["record_hash"]
                    and result["artifacts"] == _stage_artifacts(root, ledger), "Learning evidence changed")
            ledger.snapshot()
            return result
        if (root / "started.json").exists():
            return {"status": "pending", "reason": "interrupted_stage_no_automatic_optimizer_resume",
                    "deployment_authorized": False, "model_calls_submitted": 0}
        if not fixture:
            require(repo is not None, "Natural run needs credential repository")
            require(backends.readiness(benchmark_for(manifest), manifest["runtime"])["status"] == "ready",
                    "Benchmark native runtime is not ready")
        write_json(root / "started.json", seal({"identity_hash": identity["record_hash"]}))
        api = fixture_api
        steps = []
        try:
            if not fixture:
                model = manifest["model"]
                api = CachedAPI(Path(repo), root / "api", provider=model["provider"], model=model["name"],
                                workers=1, reasoning_effort=model["reasoning_effort"],
                                **model.get("transport", {"initial_health_policy": "completed_response_v1"}),
                                **({"proxy": model["proxy"]} if "proxy" in model else {}),
                                **client_options(manifest))
            write_json(root / "model_service.json", seal(api.service))
            ledger = Ledger(root, manifest, api)
            adapter = Adapter(manifest, root, ledger, fixture_evaluate=fixture_evaluate)
            train, selection = [], []
            for task in panel["tasks"]:
                role = "train" if task["family_id"] in manifest["train_families"] else "selection"
                (train if role == "train" else selection).append({"role": role, "task": task})
            current = manifest["parent_skill"]
            selected = adapter.evaluate_rows(selection, {"skill": current})
            current_score = sum(r["score"] for r in selected) / len(selected)
            initial_score = current_score
            for step in range(manifest["budget"]["max_iterations"]):
                rows = adapter.evaluate_rows(train, {"skill": current})
                traces = [{**r["trajectory"], "evidence_hash": r["output"]["evidence_hash"]} for r in rows]
                proposal = propose_native(current, traces, root / "native" / str(step), ledger,
                                          step=step, seed=manifest["seed"] + step,
                                          minibatch_size=manifest["budget"]["minibatch_size"], edit_budget=4)
                candidate = proposal["candidate_skill"]
                scores = adapter.evaluate_rows(selection, {"skill": candidate})
                candidate_score = sum(r["score"] for r in scores) / len(scores)
                gate = evaluate_gate(candidate, candidate_score, current, current_score,
                                     current, current_score, step, step + 1, metric="hard")
                step_record = seal({"step": step, "parent_skill_hash": digest(current),
                                    "proposal_hash": proposal["record_hash"],
                                    "candidate_skill_hash": digest(candidate), "parent_score": current_score,
                                    "candidate_score": candidate_score, "gate_action": gate.action,
                                    "train_tasks": len(train), "selection_tasks": len(selection),
                                    "deployment_authorized": False})
                write_json(root / "steps" / f"{step}.json", step_record)
                steps.append(step_record)
                current, current_score = gate.current_skill, gate.current_score
            payload = {"status": "completed", "candidate_skill": check_skill(current),
                       "initial_selection_score": initial_score, "selected_score": current_score,
                       "reason": "native_skillopt_development_selection"}
        except Exception as exc:
            payload = {"status": "pending", "candidate_skill": manifest["parent_skill"],
                       "reason": str(exc) if isinstance(exc, LearningPending) else type(exc).__name__}
        finally:
            if api is not None and not fixture:
                api.close()
        ledger = Ledger(root, manifest, api)
        costs = ledger.snapshot()
        if not costs["usage_complete"] and payload["status"] == "completed":
            payload.update(status="pending", candidate_skill=manifest["parent_skill"], reason="incomplete_usage")
        record = seal({"version": manifest["version"], "identity_hash": identity["record_hash"], **payload,
                       "steps": steps, "evidence_kind": manifest["evidence_kind"], "costs": costs,
                       "artifacts": _stage_artifacts(root, ledger), "deployment_authorized": False,
                       "scope_expansion_authorized": False, "resume_supported": False})
        write_json(terminal, record)
        return record
