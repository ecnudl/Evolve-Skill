"""Explicit development authorization; never reinterpret evaluation receipts."""
from __future__ import annotations

import hashlib
from pathlib import Path

from skillopt.coevolution_v5.core import seal, verify
from skillopt.continual_eval.core import (
    BENCHMARKS,
    require,
    runtime_identity,
    source_identity,
    validate_config,
)
from skillopt.continual_eval.core import (
    LONG_RESPONSE_VERSION as EVAL_LONG_RESPONSE_VERSION,
)
from skillopt.continual_eval.datasets import _asset_state, validate_panel
from skillopt.validator_pilot.api import digest

from . import GEPA_COMMIT, VERSION

BUDGET_KEYS = {"max_metric_calls", "max_reflection_calls", "max_api_calls", "max_reported_tokens",
               "max_iterations", "minibatch_size", "solver_max_tokens", "reflection_max_tokens"}
LONG_RESPONSE_VERSION = "continual-learning-v2"
MULTI_BENCHMARK_VERSION = "continual-learning-v3"
RECOVERY_VERSION = "continual-learning-v4"
MULTIDOMAIN_VERSIONS = {MULTI_BENCHMARK_VERSION, RECOVERY_VERSION}


def check_skill(text):
    require(type(text) is str and len(text.encode("utf-8")) <= 6000, "Skill must fit 6000 UTF-8 bytes")
    return text


def sources():
    own = {"continual_learning/" + p.name: hashlib.sha256(p.read_bytes()).hexdigest()
           for p in sorted(Path(__file__).parent.glob("*.py"))}
    return {**source_identity(), **own}


def manifest(panel, *, train_families, selection_families, model, budget, runtime=None,
             parent_skill="", seed=0, method="gepa", version=VERSION, recovery_policy=None):
    """Authorize new development; multi-domain feedback requires explicit v3."""
    require(version in {VERSION, LONG_RESPONSE_VERSION, *MULTIDOMAIN_VERSIONS},
            "Unsupported learning protocol version")
    multidomain = version in MULTIDOMAIN_VERSIONS
    long_response = version in {LONG_RESPONSE_VERSION, *MULTIDOMAIN_VERSIONS}
    recovery = version == RECOVERY_VERSION
    if recovery:
        from .recovery import validate_policy

        validate_policy(recovery_policy, model)
    else:
        require(recovery_policy is None, "Recovery requires an explicit v4 protocol")
    validate_panel(panel)
    benchmark = panel["benchmark"]
    require(multidomain or benchmark == "bigcodebench", "First adapter supports Coding/BigCodeBench only")
    require(all(t["partition"] == "development" for t in panel["tasks"]),
            "Only development data may reach learning; no calibration/confirmation/final")
    require(type(seed) is int and 0 <= seed < 2**32, "Invalid seed")
    require(method in {"gepa", "skillopt"}, "Unsupported learning method")
    check_skill(parent_skill)
    groups = []
    for names in (train_families, selection_families):
        require(type(names) is list and names and all(type(x) is str and x for x in names)
                and len(names) == len(set(names)), "Unique nonempty family lists required")
        groups.append(set(names))
    require(not groups[0] & groups[1], "Train/selection families overlap")
    require(set.union(*groups) == {t["family_id"] for t in panel["tasks"]},
            "Every development family must have exactly one explicit role")
    projects = {}
    for task in panel["tasks"]:
        role = "train" if task["family_id"] in groups[0] else "selection"
        if task["project_id"]:
            require(projects.setdefault(task["project_id"], role) == role, "Project crosses learning roles")
    require(type(budget) is dict and set(budget) == BUDGET_KEYS, "Explicit complete learning budget required")
    require(all(type(v) is int and v > 0 for v in budget.values()), "Positive integer budgets required")
    # Native patch reflection requests 16384 tokens. Keep this shared cap below
    # that ceiling, so GEPA and SkillOpt request the declared reflection budget.
    require(budget["reflection_max_tokens"] <= 16000
            and budget["solver_max_tokens"] <= (65536 if long_response else 16000),
            "Output budgets exceed provider protocol")
    require(type(model) is dict and model.get("max_tokens") == budget["solver_max_tokens"],
            "Solver model and budget disagree")
    runtime = {} if runtime is None else runtime
    require(type(runtime) is dict, "Runtime must be a mapping")
    # Reuse credential/proxy/model validation, but do not build an evaluation plan.
    # Reuse the existing model/runtime checks without changing the frozen v2
    # evaluation transport. V4 independently requires a 3600s recovery ceiling.
    validation_model = model
    if recovery:
        validation_model = {**model, "transport": {**model["transport"], "stream_wall_seconds": 1800}}
    validate_config({"version": EVAL_LONG_RESPONSE_VERSION if long_response else "continual-eval-v1",
                     "order": list(BENCHMARKS),
                     "panels": dict.fromkeys(BENCHMARKS), "partition": "development",
                     "methods": ["no_skill"], "histories": ["h0"], "repeats": 1,
                     "model": validation_model, "runtime": {benchmark: runtime},
                     "project_disjoint": False, "exposure_manifest": None})
    fixture = model["provider"] == "fixture"
    require((panel["provenance"] == "fixture") == fixture, "Fixture/natural provenance mismatch")
    extension = {}
    if multidomain:
        from .feedback import PROFILE

        assets = {} if fixture else _asset_state(panel)
        require(all(value["status"] == "ready" for value in assets.values()),
                "Natural learning assets must be available and match declared hashes")
        extension = {"benchmark": benchmark, "feedback_profile": PROFILE,
                     "asset_identity": assets,
                     "algorithm_implementation": "repository_native_skillopt" if method == "skillopt"
                     else "pinned_official_gepa",
                     "baseline_scope": "native_algorithm_with_benchmark_feedback_adaptation"}
    if recovery:
        extension["recovery_policy"] = dict(recovery_policy)
    return seal({"version": version, "method": method, "gepa_commit": GEPA_COMMIT, "panel_hash": digest(panel),
                 **extension,
                 "authorized_tasks": {digest(t): "train" if t["family_id"] in groups[0] else "selection"
                                      for t in panel["tasks"]},
                 "train_families": sorted(groups[0]), "selection_families": sorted(groups[1]),
                 "model": model, "budget": budget, "runtime": runtime, "seed": seed,
                 "parent_skill": parent_skill, "source_identity": sources(),
                 "host_runtime": runtime_identity(),
                 "evidence_kind": "engineering_fixture" if fixture else "natural_development_learning",
                 "feedback_authorization": "new_development_only_scalar_and_public_trace",
                 "feedback_fields": ["public", "model_output", "status", "score"],
                 "token_budget_semantics": "reported_usage_stop_with_bounded_output_per_call_overshoot",
                 "solver_workers": 1, "repeats": 1, "use_merge": False,
                 "resume_policy": "completed_replay_only_interruption_pending",
                 "deployment_authorized": False})


def validate_manifest(value, panel):
    verify(value)
    rebuilt = manifest(panel, train_families=value["train_families"],
                       selection_families=value["selection_families"], model=value["model"],
                       budget=value["budget"], runtime=value["runtime"], parent_skill=value["parent_skill"],
                       seed=value["seed"], method=value["method"], version=value["version"],
                       recovery_policy=value.get("recovery_policy"))
    require(value == rebuilt, "Learning manifest, sources, data or authorization changed")
    return value
