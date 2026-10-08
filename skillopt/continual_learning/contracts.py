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
DELIVERY_VERSION = "continual-learning-v5"
HARDENED_VERSION = "continual-learning-v6"
BUDGET_VERSION = "continual-learning-v7"
# V8 (generalization gate): selection on the canonical val part, a frozen paired
# win margin, labeled failure feedback for both methods, concurrent solver rows.
GENERALIZATION_VERSION = "continual-learning-v8"
# V9: v8 with the two-pass paired sign-test gate (screen on the first val pass, confirm on a
# fresh val pass of parent and candidate); everything else is shared with v8.
CONFIRMATION_VERSION = "continual-learning-v9"
# V10 (main method): the v9 protocol with label-free Rubric -> probe -> Research verifier feedback
# on failed train rows (method ``rubric_research``); the verifier's own model calls are a separate
# ledger role with its own budget keys.
VERIFIER_VERSION = "continual-learning-v10"
VERIFIER_METHOD = "rubric_research"
VERIFIER_BUDGET_KEYS = {"max_verifier_calls", "verifier_max_tokens"}
GENERALIZATION_VERSIONS = {GENERALIZATION_VERSION, CONFIRMATION_VERSION, VERIFIER_VERSION}
# V9 and v10 share the two-pass sign-test gate and the fresh confirmation rollouts.
CONFIRMATION_VERSIONS = {CONFIRMATION_VERSION, VERIFIER_VERSION}
RAISED_BUDGET_VERSIONS = {BUDGET_VERSION, *GENERALIZATION_VERSIONS}
HARDENED_VERSIONS = {HARDENED_VERSION, *RAISED_BUDGET_VERSIONS}
DELIVERY_VERSIONS = {DELIVERY_VERSION, *HARDENED_VERSIONS}
COMMON_SKILL_BUDGET = 6000
RECOVERY_VERSIONS = {RECOVERY_VERSION, *DELIVERY_VERSIONS}
MULTIDOMAIN_VERSIONS = {MULTI_BENCHMARK_VERSION, *RECOVERY_VERSIONS}
# Learning roles by partition: train evidence is always development data; v8
# selects on the canonical val part (project partition skill_confirmation).
SELECTION_PARTITIONS = dict.fromkeys(GENERALIZATION_VERSIONS, "skill_confirmation")


def check_skill(text, limit=COMMON_SKILL_BUDGET):
    require(type(text) is str and len(text.encode("utf-8")) <= limit, f"Skill must fit {limit} UTF-8 bytes")
    return text


def skill_budget(manifest):
    """Frozen Skill interface in UTF-8 bytes; only v7/v8 raise the common 6000-byte budget."""
    if manifest.get("version") in RAISED_BUDGET_VERSIONS:
        return manifest["recovery_policy"]["skill_budget_bytes"]
    return COMMON_SKILL_BUDGET


def role_partition(version, role):
    """Partition a learning role's tasks must carry: development, except v8 selection = val."""
    require(role in {"train", "selection"}, "Unknown learning role")
    if role == "selection":
        return SELECTION_PARTITIONS.get(version, "development")
    return "development"


def sources():
    own = {"continual_learning/" + p.name: hashlib.sha256(p.read_bytes()).hexdigest()
           for p in sorted(Path(__file__).parent.glob("*.py"))}
    # The v10 verifier retrieves documentation through the pilot's extractor; freeze it too.
    research = Path(__file__).resolve().parents[1] / "validator_pilot" / "research.py"
    own["validator_pilot/research.py"] = hashlib.sha256(research.read_bytes()).hexdigest()
    return {**source_identity(), **own}


def manifest(panel, *, train_families, selection_families, model, budget, runtime=None,
             parent_skill="", seed=0, method="gepa", version=VERSION, recovery_policy=None,
             feedback_profile=None, parent_verifier_policy=None):
    """Authorize new development; multi-domain feedback requires explicit v3."""
    require(version in {VERSION, LONG_RESPONSE_VERSION, *MULTIDOMAIN_VERSIONS},
            "Unsupported learning protocol version")
    multidomain = version in MULTIDOMAIN_VERSIONS
    long_response = version in {LONG_RESPONSE_VERSION, *MULTIDOMAIN_VERSIONS}
    recovery = version in RECOVERY_VERSIONS
    verifier = version == VERIFIER_VERSION
    if recovery:
        from .recovery import validate_policy

        validate_policy(recovery_policy, model, version)
        require(version not in {DELIVERY_VERSION, HARDENED_VERSION} or method == "skillopt",
                "Learning v5/v6 defines SkillOpt-only over-budget handling")
    else:
        require(recovery_policy is None, "Recovery requires an explicit v4 protocol")
    validate_panel(panel)
    benchmark = panel["benchmark"]
    require(multidomain or benchmark == "bigcodebench", "First adapter supports Coding/BigCodeBench only")
    require(type(seed) is int and 0 <= seed < 2**32, "Invalid seed")
    require(method in {"gepa", "skillopt", VERIFIER_METHOD}, "Unsupported learning method")
    # The verifier method and the v10 protocol imply each other: v10 is the only version whose
    # feedback comes from the verifier, and the verifier only runs under v10's budget and policy.
    require((method == VERIFIER_METHOD) == verifier, "The rubric_research method requires learning v10 and vice versa")
    if verifier:
        from .verifier import validate_policy_mapping

        # The co-evolving verification policies (by domain) a chained stage starts from -- its own
        # domain's entry, else the frozen domain default; the stage hands the mapping on with its
        # domain's entry replaced by the policy it ended with (other domains' entries verbatim).
        require(parent_verifier_policy is None or validate_policy_mapping(parent_verifier_policy, benchmark),
                "Invalid parent verifier policy")
    else:
        require(parent_verifier_policy is None, "Verifier policies are a learning v10 concept")
    check_skill(parent_skill, recovery_policy["skill_budget_bytes"] if version in RAISED_BUDGET_VERSIONS
                else COMMON_SKILL_BUDGET)
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
        # Train evidence is development data only; v8 selects on the canonical
        # val part (skill_confirmation). Calibration and final never reach learning.
        require(task["partition"] == role_partition(version, role),
                "Only development data may reach learning; no calibration/confirmation/final")
        if task["project_id"]:
            require(projects.setdefault(task["project_id"], role) == role, "Project crosses learning roles")
    require(type(budget) is dict and set(budget) == (BUDGET_KEYS | VERIFIER_BUDGET_KEYS if verifier else BUDGET_KEYS),
            "Explicit complete learning budget required")
    require(all(type(v) is int and v > 0 for v in budget.values()), "Positive integer budgets required")
    # Native patch reflection requests 16384 tokens. Keep this shared cap below
    # that ceiling, so GEPA and SkillOpt request the declared reflection budget.
    require(budget["reflection_max_tokens"] <= 16000
            and budget["solver_max_tokens"] <= (65536 if long_response else 16000)
            and budget.get("verifier_max_tokens", 1) <= 16000,
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
        from .execution_evidence import PROFILE as EVIDENCE_PROFILE
        from .feedback import LABELED_PROFILE, PROFILE, VERIFIER_PROFILE

        feedback_profile = feedback_profile or PROFILE
        require(feedback_profile == PROFILE or (
            feedback_profile == EVIDENCE_PROFILE and version == BUDGET_VERSION
            and benchmark == "bigcodebench" and method == "skillopt")
            or (feedback_profile == LABELED_PROFILE and version in GENERALIZATION_VERSIONS and not verifier)
            or (feedback_profile == VERIFIER_PROFILE and verifier),
            "Execution-evidence feedback is a v7 BigCodeBench SkillOpt ablation only; "
            "labeled failure feedback is v8/v9 only; verifier feedback is v10 only")
        if verifier:
            require(feedback_profile == VERIFIER_PROFILE, "Learning v10 uses label-free verifier feedback")
        elif version in GENERALIZATION_VERSIONS:
            require(feedback_profile == LABELED_PROFILE, "Learning v8 uses labeled failure feedback for both methods")
        assets = {} if fixture else _asset_state(panel)
        require(all(value["status"] == "ready" for value in assets.values()),
                "Natural learning assets must be available and match declared hashes")
        extension = {"benchmark": benchmark, "feedback_profile": feedback_profile,
                     "asset_identity": assets,
                     "algorithm_implementation": "repository_native_skillopt" if method == "skillopt"
                     else "pinned_official_gepa" if method == "gepa"
                     else "repository_native_skillopt_updater_with_rubric_probe_research_verifier",
                     "baseline_scope": "native_algorithm_with_benchmark_feedback_adaptation" if not verifier
                     else "main_method_label_free_verifier_feedback_same_updater_and_gate_as_v9"}
    else:
        require(feedback_profile is None, "Feedback profiles require a multi-domain learning version")
    if recovery:
        extension["recovery_policy"] = dict(recovery_policy)
    solver_workers = 1
    if version in GENERALIZATION_VERSIONS:
        solver_workers = recovery_policy["solver_workers"]
        extension["selection_partition"] = role_partition(version, "selection")
        extension["feedback_fields"] = ["public", "model_output", "status", "score",
                                        "verifier_probe_reports_on_failed_train_rows" if verifier else
                                        "expected_or_execution_evidence_on_failed_train_rows"]
    if verifier:
        extension["parent_verifier_policy"] = parent_verifier_policy
    return seal({"version": version, "method": method, "gepa_commit": GEPA_COMMIT, "panel_hash": digest(panel),
                 "authorized_tasks": {digest(t): "train" if t["family_id"] in groups[0] else "selection"
                                      for t in panel["tasks"]},
                 "train_families": sorted(groups[0]), "selection_families": sorted(groups[1]),
                 "model": model, "budget": budget, "runtime": runtime, "seed": seed,
                 "parent_skill": parent_skill, "source_identity": sources(),
                 "host_runtime": runtime_identity(),
                 "evidence_kind": "engineering_fixture" if fixture else "natural_development_learning",
                 "feedback_authorization": "new_development_only_scalar_and_public_trace"
                 if version not in GENERALIZATION_VERSIONS else
                 "new_development_label_free_verifier_reports_on_failed_train_rows_val_selection_scalar_only"
                 if verifier else
                 "new_development_train_labels_on_failed_rows_val_selection_scalar_only",
                 "feedback_fields": ["public", "model_output", "status", "score"],
                 "token_budget_semantics": "reported_usage_stop_with_bounded_output_per_call_overshoot",
                 "solver_workers": solver_workers, "repeats": 1, "use_merge": False,
                 "resume_policy": "completed_replay_only_interruption_pending",
                 "deployment_authorized": False, **extension})


def validate_manifest(value, panel):
    verify(value)
    rebuilt = manifest(panel, train_families=value["train_families"],
                       selection_families=value["selection_families"], model=value["model"],
                       budget=value["budget"], runtime=value["runtime"], parent_skill=value["parent_skill"],
                       seed=value["seed"], method=value["method"], version=value["version"],
                       recovery_policy=value.get("recovery_policy"), feedback_profile=value.get("feedback_profile"),
                       parent_verifier_policy=value.get("parent_verifier_policy"))
    require(value == rebuilt, "Learning manifest, sources, data or authorization changed")
    return value
