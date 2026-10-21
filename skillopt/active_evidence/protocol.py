"""The sealed v11 protocol record.

The frozen ledger, solver adapter, feedback projection and native bridge gate their behavior on the learning
version string (``continual-learning-v10`` enables the verifier call role, concurrent rows, hardened accounting and
strict analyst parsing), and ``contracts.manifest`` refuses an empty selection role. This mode therefore builds a
v10-SHAPED execution record itself -- the same fields and checks, but ``selection_families == []`` (no canonical
validation split is read or authorized) and every development task authorized under the low-level ``train`` role;
the development families are split into step families and a fixed reserved challenge pool that serves the
post-update selection (held out from diagnosis, reflection and Research) -- and carries
its real identity in the ``active_evidence`` extension: protocol, step/challenge split of the authorized families,
arms, per-step limits, rollout import binding and the hashes of this package, the native updater and the executed
code closure. The split is enforced by the package (``stage.bind_step_rows``): a challenge task can be solved by
the adapter but never enters reflection or diagnosis."""
from __future__ import annotations

import ast
import hashlib
import re
from pathlib import Path

from skillopt.coevolution_v5.core import seal, verify
from skillopt.continual_eval.core import BENCHMARKS, require, runtime_identity, validate_config
from skillopt.continual_eval.core import LONG_RESPONSE_VERSION as EVAL_LONG_RESPONSE_VERSION
from skillopt.continual_eval.datasets import _asset_state, validate_panel
from skillopt.continual_learning import GEPA_COMMIT
from skillopt.continual_learning.contracts import (
    BUDGET_KEYS,
    VERIFIER_BUDGET_KEYS,
    VERIFIER_METHOD,
    VERIFIER_VERSION,
    check_skill,
    sources,
)
from skillopt.continual_learning.feedback import VERIFIER_PROFILE
from skillopt.continual_learning.recovery import POLICY_V10, validate_policy
from skillopt.continual_learning.skillopt import native_sources
from skillopt.validator_pilot.api import digest

from . import METHOD, MODULES, PROTOCOL
from .profiles import PROFILE_VERSION, PROFILES, supported

FEEDBACK_ARMS = ("scalar", "diagnosis", "diagnosis_research", "hidden_failure")
POST_UPDATE_ARMS = ("none", "challenge_replay", "matched_scalar_branch", "matched_selection_branch")
STUDY_ARMS = ("matched_scalar_branch", "matched_selection_branch")  # studies deploy nothing
CHALLENGE_ARMS = ("challenge_replay",) + STUDY_ARMS  # arms that evaluate on a panel from the reserved pool
# How a step's candidate text is chosen: "native" = the native updater's candidate; "screened" = one exact text
# selected by the composition-aware screen on the step rows (screen.py), or abstention.
UPDATE_MODES = ("native", "screened")
# The four registered controls (shared parent, step subset, seed, updater, information permissions, budget rule).
REGISTERED_ARMS = (
    {"feedback": "scalar", "post_update": "none"},
    {"feedback": "diagnosis", "post_update": "none"},
    {"feedback": "diagnosis_research", "post_update": "none"},
    {"feedback": "diagnosis_research", "post_update": "challenge_replay"},
    # the bounded development failure-message study (label feedback; never the method): the message branch against a
    # matched scalar branch from the same traces, both solved on a drawn development holdout, nothing deployed
    {"feedback": "hidden_failure", "post_update": "matched_scalar_branch"},
    # the same matched design with the method's own feedback as the treatment branch (a powered paired test of the
    # diagnosis package against the scalar package; nothing deployed)
    {"feedback": "diagnosis_research", "post_update": "matched_scalar_branch"},
)
DEFAULT_LIMITS = {
    "view_rows": 16, "view_output_chars": 3000,
    "max_hypotheses": 4, "max_checks_per_case": 2, "max_diagnoser_calls_per_step": 2, "max_research_pages": 3,
    # decision rule v2 (decision.py): a family-level one-sided sign test on the fresh panel; the operating point was
    # chosen on development evidence (design memo of 2026-10-10) and is frozen prospectively
    "fresh_tasks": 96, "replay_rows": 32, "local_fix_rows": 8,
    "min_paired_known": 87, "decision_alpha_permille": 50,
    # the composition-aware screen (update_mode "screened"): a screening threshold on analyst-seen rows, not a
    # confirmation level
    "screen_alpha_permille": 100,
    "edit_budget": 4, "report_chars": 1800, "summary_chars": 2500,
    "restriction_attempts": 0,
}
LIMIT_RANGES = {
    "view_rows": (1, 64), "view_output_chars": (200, 20000),
    "max_hypotheses": (1, 8), "max_checks_per_case": (1, 2), "max_diagnoser_calls_per_step": (1, 4),
    "max_research_pages": (0, 3),
    "fresh_tasks": (0, 500), "replay_rows": (0, 500), "local_fix_rows": (0, 500),
    "min_paired_known": (1, 500), "decision_alpha_permille": (1, 200), "screen_alpha_permille": (1, 500),
    "edit_budget": (1, 16), "report_chars": (200, 1800), "summary_chars": (200, 4000),
    "restriction_attempts": (0, 0),  # the scoped-revision path is deferred (docs/learning-v11-active-evidence)
}
# Optional limits: absent unless a stage asks for them (a default stage's limits are exactly DEFAULT_LIMITS).
# ``train_panel_rows`` sizes the in-sample shadow measurement of the post-update challenge (challenge.py): an
# outcome-blind sample of the step roster re-solved by both Skills; the acting decision never reads it.
OPTIONAL_LIMIT_RANGES = {"train_panel_rows": (1, 500)}
# Entry modules of the executed code closure (the stage orchestration and the native updater's own modules).
CODE_ENTRIES = ("skillopt/active_evidence/stage.py",)
ROLLOUT_SOURCE_KEYS = {"learning_dir", "manifest_hash", "result_hash", "step"}
INFORMATION_BOUNDARIES = {
    "authorized_partitions": ["development"],
    "selection_role": "no canonical validation split and no repeated full-panel validation; the post-update decision "
                      "uses a fresh panel sampled from the fixed reserved development challenge pool (a selection "
                      "function) plus replay rows as a harm check; all of it is learning-process data",
    "challenge_pool": "fixed reserved development families, disjoint from the step families and held out from diagnosis, "
                      "reflection and Research; a panel is drawn from it after the candidate is frozen",
    "final_or_held_out": "the canonical validation, final and calibration partitions are never authorized, imported, "
                         "replayed or used for any selection",
    "private_scoring_data": "never in a model payload (hidden-test tracebacks stay host-only)",
}
# The matched-branch study evaluates both frozen candidates on a drawn development holdout (the reused challenge
# pool): no replay or local-fix sets, at least 90% of the drawn positions jointly known.
MATCHED_LIMITS = {"fresh_tasks": 242, "replay_rows": 0, "local_fix_rows": 0, "min_paired_known": 218}
# Evaluation-only reference Skills of the matched-branch study (study v2): the stage's parent always, plus at most
# this many named frozen Skills (e.g. the Skill a validation-gated baseline stage deployed). Each solves the drawn
# holdout once under its own rollout key; none is updated, deployed, or shown to a diagnoser, analyst or Research.
MAX_REFERENCE_SKILLS = 4
REFERENCE_NAME = re.compile(r"[a-z][a-z0-9_]{0,31}")
REFERENCE_RESERVED = frozenset({"parent", "comparator", "treatment", "current", "candidate"})
HOLDOUT_REFERENCES = ("matched-branch study: the parent Skill and the additional named reference Skills solve the "
                      "drawn holdout (evaluation only, after both candidates are frozen); a named reference is never "
                      "updated, deployed or shown to a diagnoser, analyst or Research (the parent is the ordinary "
                      "starting Skill of both updater branches)")
# The failure-message study arm replaces the private-scoring promise above with this sealed release profile.
RELEASE_PROFILE = {
    "version": "development-failure-messages-v1",
    "released_to": "analysts of the message branch only (reflection role), for FAILED development step rows",
    "content": "hidden-test names and the final exception message text of their failing hidden tests (expected/actual "
               "values inside messages included); traceback frames, absolute paths and source lines removed; at most 4 "
               "tests per row in sorted test-name order, 400 chars per test, row text bounded like an evidence report",
    "never": "hidden test code, canonical solutions, reference answers; nothing to the solver beyond the frozen Skill and "
             "the ordinary task input; nothing about challenge-pool or final tasks",
    "withheld": "tracebacks without an exception-class line; any message or row failing the forbidden-content check",
    "audit": "diagnosis/<step>/release_audit.json is sealed before any updater call; fewer than half of the failed rows "
             "released -> failed_delivery (the step stops without an updater call)",
}


def sampling_identity(value):
    """The identity that seeds a stage's challenge draws and execution orders: the sealed manifest hash -- for a
    manifest that carries optional limits, the hash the SAME manifest has without them. An optional measurement
    therefore never changes which fresh tasks are drawn, their order, or the balanced halves of the acting sets."""
    limits = value["active_evidence"]["limits"]
    optional = set(limits) & set(OPTIONAL_LIMIT_RANGES)
    if not optional:
        return value["record_hash"]
    base = {k: v for k, v in value.items() if k != "record_hash"}
    base["active_evidence"] = {**value["active_evidence"],
                               "limits": {k: v for k, v in limits.items() if k not in optional}}
    return seal(base)["record_hash"]


def min_known(fresh):
    """The coverage a fresh panel needs for an admissible decision: ceil(90% of its positions)."""
    return -(-9 * fresh // 10)


def default_limits(arms):
    base = dict(DEFAULT_LIMITS)
    if arms.get("post_update") in STUDY_ARMS:
        base.update(MATCHED_LIMITS)
    return base


def effective_limits(arms, eligible_fresh):
    """The requested defaults with the fresh panel capped by the eligible challenge-pool tasks, fixed before any
    challenge outcome exists: n_eff = min(requested, eligible), min_paired_known = ceil(0.90 * n_eff). Replay and
    local-fix counts are capped at draw time by the available passed / failed step rows and never reduce the fresh
    count. A smaller pool lowers power; alpha is never relaxed."""
    limits = default_limits(arms)
    if arms.get("post_update") in CHALLENGE_ARMS:
        require(type(eligible_fresh) is int and eligible_fresh >= 1, "A challenge arm needs an eligible fresh task")
        limits["fresh_tasks"] = min(limits["fresh_tasks"], eligible_fresh)
        limits["min_paired_known"] = min_known(limits["fresh_tasks"])
    return limits


def information_boundaries(arms):
    base = dict(INFORMATION_BOUNDARIES)
    if arms["post_update"] in STUDY_ARMS:
        base["holdout_references"] = HOLDOUT_REFERENCES
    if arms["feedback"] != "hidden_failure":
        return base
    return {**base,
            "private_scoring_data": "label-feedback study arm: bounded hidden-test failure messages of FAILED development "
                                    "step rows reach the message-branch analysts under the sealed release profile; "
                                    "everything else stays host-only",
            "release_profile": RELEASE_PROFILE}


def package_sources():
    package = Path(__file__).resolve().parent
    return {"active_evidence/" + name: hashlib.sha256((package / name).read_bytes()).hexdigest()
            for name in sorted(MODULES)}


def code_closure():
    """Every repository module a run can execute, by content hash: the transitive import closure (``skillopt.*`` and
    ``scripts.*``, absolute and relative imports, function-level imports, enclosing package ``__init__`` files) of
    the entry modules and the native updater's modules. A new import enters automatically."""
    repo = Path(__file__).resolve().parents[2]

    def target(name):
        parts = name.split(".")
        if parts[0] not in {"skillopt", "scripts"}:
            return None
        path = repo.joinpath(*parts)
        return path.with_suffix(".py") if path.with_suffix(".py").is_file() else (
            path / "__init__.py" if (path / "__init__.py").is_file() else None)

    todo = [repo / entry for entry in CODE_ENTRIES]
    todo += [repo / "skillopt" / name for name in native_sources() if name.endswith(".py")]
    seen = set()
    while todo:
        path = todo.pop()
        if path in seen:
            continue
        seen.add(path)
        relative = path.relative_to(repo)
        for depth in range(1, len(relative.parts)):
            init = repo.joinpath(*relative.parts[:depth], "__init__.py")
            if init.is_file():
                todo.append(init)
        module = list(relative.with_suffix("").parts)
        if module[-1] == "__init__":
            module = module[:-1]
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            names = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    base = module[: len(module) - node.level + (path.name == "__init__.py")]
                    prefix = ".".join(base + ([node.module] if node.module else []))
                else:
                    prefix = node.module or ""
                names = [prefix] + [prefix + "." + alias.name for alias in node.names]
            for name in names:
                found = target(name)
                if found is not None and found not in seen:
                    todo.append(found)
    return {str(path.relative_to(repo)): hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(seen)}


def validate_arms(arms):
    require(type(arms) is dict and set(arms) == {"feedback", "post_update"}
            and arms["feedback"] in FEEDBACK_ARMS and arms["post_update"] in POST_UPDATE_ARMS,
            "Arms must name a feedback arm and a post-update arm")
    require((arms["feedback"] != "hidden_failure" or arms["post_update"] == "matched_scalar_branch")
            and (arms["post_update"] != "matched_scalar_branch" or arms["feedback"] != "scalar"),
            "The failure-message arm runs only as the matched-branch study, and the study needs a non-scalar "
            "treatment branch (its comparator is the scalar package)")
    return {"feedback": arms["feedback"], "post_update": arms["post_update"]}


def validate_update_mode(mode, arms):
    require(mode in UPDATE_MODES, "update_mode is native or screened")
    require((arms["post_update"] == "matched_selection_branch") <= (mode == "screened"),
            "The selection study compares the screen's selection with the native candidate: it needs update_mode screened")
    require(mode == "native" or arms["feedback"] != "hidden_failure", "The failure-message study arm is not screened")
    return mode


def validate_limits(limits, arms):
    require(type(limits) is dict and set(limits) - set(OPTIONAL_LIMIT_RANGES) == set(DEFAULT_LIMITS),
            "Explicit complete limits required")
    for key, value in limits.items():
        low, high = (LIMIT_RANGES if key in LIMIT_RANGES else OPTIONAL_LIMIT_RANGES)[key]
        require(type(value) is int and low <= value <= high, f"Limit {key} out of range [{low}, {high}]")
    require("train_panel_rows" not in limits or arms["post_update"] == "challenge_replay",
            "The in-sample train panel belongs to the method's post-update challenge only")
    if arms["post_update"] in CHALLENGE_ARMS:
        require(limits["fresh_tasks"] >= limits["min_paired_known"] >= min_known(limits["fresh_tasks"]),
                "A challenge needs min_paired_known between 90% of the fresh panel and its size")
    if arms["post_update"] in STUDY_ARMS:
        require(limits["replay_rows"] == 0 and limits["local_fix_rows"] == 0,
                "A matched study has no replay or local-fix set (it compares two candidates on the holdout only)")
    return dict(limits)


def _families(panel, step_families, challenge_families, arms):
    groups = []
    for name, names in (("step", step_families), ("challenge", challenge_families)):
        require(type(names) is list and all(type(x) is str and x for x in names) and len(names) == len(set(names)),
                f"Unique family list required for the {name} role")
        groups.append(set(names))
    require(groups[0], "The step subset needs at least one family")
    require(groups[1] or arms["post_update"] == "none", "A challenge arm needs a nonempty challenge pool")
    require(not groups[0] & groups[1], "Step/challenge families overlap")
    require(set.union(*groups) == {t["family_id"] for t in panel["tasks"]},
            "Every panel family must be a step family or a challenge family")
    projects = {}
    for task in panel["tasks"]:
        require(task["partition"] == "development",
                "Only development data may reach this mode; no calibration/confirmation/final partition")
        role = "step" if task["family_id"] in groups[0] else "challenge"
        if task["project_id"]:
            require(projects.setdefault(task["project_id"], role) == role, "Project crosses step/challenge roles")
    return groups


def _validate_rollout_source(value):
    if value is None:
        return None
    require(type(value) is dict and set(value) == ROLLOUT_SOURCE_KEYS and type(value["learning_dir"]) is str
            and value["learning_dir"] and all(type(value[k]) is str and len(value[k]) == 64 for k in ("manifest_hash", "result_hash"))
            and value["step"] == 0, "A rollout source names a sealed learning directory, its hashes and step 0")
    return dict(value)


def validate_references(references, arms):
    """Named evaluation-only Skills with their (tool-supplied) provenance; only the matched-branch study has them."""
    references = [] if references is None else references
    require(type(references) is list and len(references) <= MAX_REFERENCE_SKILLS,
            f"At most {MAX_REFERENCE_SKILLS} reference Skills")
    require(not references or arms["post_update"] in STUDY_ARMS,
            "Reference Skills belong to the matched-branch study")
    names, out = set(), []
    for ref in references:
        require(type(ref) is dict and set(ref) == {"name", "skill", "source"} and type(ref["name"]) is str
                and REFERENCE_NAME.fullmatch(ref["name"]) is not None and ref["name"] not in REFERENCE_RESERVED
                and ref["name"] not in names and type(ref["source"]) is dict and ref["source"],
                "A reference Skill needs a unique lower-case name, its text and a provenance record")
        check_skill(ref["skill"], POLICY_V10["skill_budget_bytes"])
        names.add(ref["name"])
        out.append({"name": ref["name"], "skill": ref["skill"], "source": dict(ref["source"])})
    return out


def manifest(panel, *, step_families, challenge_families, model, budget, runtime=None, parent_skill="", seed=0,
             arms, limits=None, rollout_source=None, reference_skills=None, update_mode="native",
             analyst_profile="native"):
    """Authorize one v11 stage: a v10-shaped record for the frozen ledger/adapter plus the mode's extension."""
    arms = validate_arms(arms)
    update_mode = validate_update_mode(update_mode, arms)
    from .updater import ANALYST_PROFILES

    require(analyst_profile in ANALYST_PROFILES, "Unknown analyst prompt profile")
    require(analyst_profile == "native" or (arms["feedback"] == "scalar" and update_mode == "native"),
            "An analyst prompt profile is exercised with pass/fail feedback and the native update only")
    limits = validate_limits(dict(DEFAULT_LIMITS) if limits is None else limits, arms)
    reference_skills = validate_references(reference_skills, arms)
    validate_policy(POLICY_V10, model, VERIFIER_VERSION)
    validate_panel(panel)
    benchmark = panel["benchmark"]
    require(supported(benchmark), f"{benchmark}: the active-evidence mode has no diagnostic adapter (unsupported); "
                                  "use the old modes")
    # a benchmark whose profile lists its arms implements only those (refused here, before any call)
    require(arms in PROFILES[benchmark].get("arms", [arms]),
            f"{benchmark}: this active-evidence arm is not implemented for the benchmark")
    require(type(seed) is int and 0 <= seed < 2**32, "Invalid seed")
    check_skill(parent_skill, POLICY_V10["skill_budget_bytes"])
    groups = _families(panel, step_families, challenge_families, arms)
    require(type(budget) is dict and set(budget) == BUDGET_KEYS | VERIFIER_BUDGET_KEYS,
            "Explicit complete learning budget (with the verifier role) required")
    require(all(type(v) is int and v > 0 for v in budget.values()), "Positive integer budgets required")
    require(budget["max_iterations"] <= 100, "Step rollout keys 0..99 never collide with challenge keys (1000+)")
    require(budget["reflection_max_tokens"] <= 16000 and budget["solver_max_tokens"] <= 65536
            and budget["verifier_max_tokens"] <= 16000, "Output budgets exceed provider protocol")
    require(type(model) is dict and model.get("max_tokens") == budget["solver_max_tokens"],
            "Solver model and budget disagree")
    runtime = {} if runtime is None else runtime
    require(type(runtime) is dict, "Runtime must be a mapping")
    validation_model = {**model, "transport": {**model["transport"], "stream_wall_seconds": 1800}}
    validate_config({"version": EVAL_LONG_RESPONSE_VERSION, "order": list(BENCHMARKS),
                     "panels": dict.fromkeys(BENCHMARKS), "partition": "development",
                     "methods": ["no_skill"], "histories": ["h0"], "repeats": 1,
                     "model": validation_model, "runtime": {benchmark: runtime},
                     "project_disjoint": False, "exposure_manifest": None})
    fixture = model["provider"] == "fixture"
    require((panel["provenance"] == "fixture") == fixture, "Fixture/natural provenance mismatch")
    assets = {} if fixture else _asset_state(panel)
    require(all(value["status"] == "ready" for value in assets.values()),
            "Natural learning assets must be available and match declared hashes")
    extension = {"protocol": PROTOCOL, "method": METHOD, "profile_version": PROFILE_VERSION,
                 "step_families": sorted(groups[0]), "challenge_families": sorted(groups[1]),
                 "arms": arms, "limits": limits, "rollout_source": _validate_rollout_source(rollout_source),
                 "reference_skills": reference_skills, "update_mode": update_mode,
                 # absent for the unchanged package, so that default manifests keep their shape
                 **({} if analyst_profile == "native" else {"analyst_profile": analyst_profile}),
                 "policy_lifecycle": "frozen", "information_boundaries": information_boundaries(arms),
                 "package_sources": package_sources(), "native_sources": native_sources(),
                 "code_closure": code_closure()}
    return seal({"version": VERIFIER_VERSION, "method": VERIFIER_METHOD, "gepa_commit": GEPA_COMMIT,
                 "panel_hash": digest(panel),
                 "authorized_tasks": {digest(t): "train" for t in panel["tasks"]},
                 "train_families": sorted(groups[0] | groups[1]), "selection_families": [],
                 "model": model, "budget": budget, "runtime": runtime, "seed": seed,
                 "parent_skill": parent_skill, "source_identity": sources(), "host_runtime": runtime_identity(),
                 "evidence_kind": "engineering_fixture" if fixture else "natural_development_learning",
                 "feedback_authorization": "new_development_only_itemized_evidence_reports_no_fixed_validation_gate",
                 "feedback_fields": ["public", "model_output", "status", "score",
                                     "itemized_evidence_reports_on_step_rows"],
                 "token_budget_semantics": "reported_usage_stop_with_bounded_output_per_call_overshoot",
                 "solver_workers": POLICY_V10["solver_workers"], "repeats": 1, "use_merge": False,
                 "resume_policy": "completed_replay_only_interruption_pending", "deployment_authorized": False,
                 "benchmark": benchmark, "feedback_profile": VERIFIER_PROFILE, "asset_identity": assets,
                 "algorithm_implementation": "repository_native_skillopt_updater_with_active_evidence_diagnosis",
                 "baseline_scope": "active_evidence_mode_v10_shaped_compatibility_record_no_selection_role",
                 "recovery_policy": dict(POLICY_V10), "selection_partition": "none_no_fixed_validation_gate",
                 "parent_verifier_policy": None, "active_evidence": extension})


def validate_manifest(value, panel):
    """A sealed v11 record rebuilt from its own inputs must be identical (sources, data, authorization, code)."""
    verify(value)
    require(type(value.get("active_evidence")) is dict and value["active_evidence"].get("protocol") == PROTOCOL,
            "Not an active-evidence manifest")
    extension = value["active_evidence"]
    rebuilt = manifest(panel, step_families=extension["step_families"], challenge_families=extension["challenge_families"],
                       model=value["model"], budget=value["budget"], runtime=value["runtime"],
                       parent_skill=value["parent_skill"], seed=value["seed"], arms=extension["arms"],
                       limits=extension["limits"], rollout_source=extension["rollout_source"],
                       reference_skills=extension.get("reference_skills"),
                       update_mode=extension.get("update_mode", "native"),
                       analyst_profile=extension.get("analyst_profile", "native"))
    require(value == rebuilt, "Active-evidence manifest, sources, data, authorization or code changed")
    return value


def step_items(value, panel):
    families = set(value["active_evidence"]["step_families"])
    return [{"role": "train", "task": t} for t in panel["tasks"] if t["family_id"] in families]


def challenge_items(value, panel):
    families = set(value["active_evidence"]["challenge_families"])
    return [{"role": "train", "task": t} for t in panel["tasks"] if t["family_id"] in families]
