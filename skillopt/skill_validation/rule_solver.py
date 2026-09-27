"""Rule exposure adapter for the existing public-check/single-revision solver.

There is one solver protocol, inherited unchanged from ``public_revision``.
The extra immutable record binds a structured rule version to its effective
text, since different histories can legitimately render the very same prompt.
This is shadow execution, not a Skill admission or deployment decision.
"""
from __future__ import annotations

import hashlib

from skillopt.coevolution_v5.core import seal

from . import public_revision
from .models import require
from .panel import checked_path
from .rule_skill import RuleSkill, render_for_task, render_skill
from .solver_profile import SolverProfile

VERSION = "conditional-rule-public-revision-adapter-v1"


def solve_rule_condition(row, skill, condition, repeat, calls, executor, root, *, exposure="conditional",
                         solver_profile=None):
    """Expose rules, generate once, publicly check, and offer at most one repair.

    Only ``task``, ``public_task`` and ``public_wrapper`` are read from ``row``.
    The returned ``revision`` is the unchanged result of ``revise_public``.
    No-Skill requires an actually empty rule set, not merely a filtered one.
    Replays use existing model-call caches and public execution receipts; they
    cannot rebind a position directory to a different rule history or scope.
    """
    profile = SolverProfile() if solver_profile is None else solver_profile
    require(type(profile) is SolverProfile, "Typed SolverProfile required")
    if profile.enabled:
        require(calls.api.service.get("initial_health_policy") == profile.to_dict()["initial_health_policy"],
                "API health policy differs from the frozen solver profile")
        require(all(getattr(calls, "output_token_limits", {}).get(kind) == cap
                    for kind, cap in profile.output_token_limits().items()),
                "Solver call budgets differ from the frozen solver profile")
    require(type(skill) is RuleSkill, "Typed RuleSkill required")
    require(type(condition) is str and condition in {"no_skill", "current", "candidate"},
            "Unknown solver condition")
    require(type(repeat) is int and repeat >= 0, "Nonnegative repeat required")
    require(type(exposure) is str and exposure in {"raw", "conditional"}, "Unknown rule exposure mode")
    require(condition != "no_skill" or not skill.rules, "No-Skill requires an empty rule set")
    public_row = {name: row[name] for name in ("task", "public_task", "public_wrapper")}
    task, public_task, wrapper = public_revision._parts(public_row)
    if exposure == "conditional":
        rendering = render_for_task(skill, task)
    else:
        rendering = {"text": render_skill(skill), "selected_rule_ids": [r.id for r in skill.rules],
                     "disabled_rule_ids": [], "scope_basis": "all_rules_exposed_diagnostic_no_applicability_filter",
                     "deployment_authorized": False}
    text = rendering["text"]
    text_hash = hashlib.sha256(text.encode()).hexdigest()
    mapping = seal({"version": VERSION, "rule_skill_hash": skill.content_hash, "history_id": skill.history_id,
        "effective_skill_text_hash": text_hash, "exposure_mode": exposure, "rendering": rendering,
        "task_hash": task.contract.content_hash, "callable_task_hash": task.content_hash,
        "public_task_hash": public_task.content_hash, "public_wrapper_hash": wrapper.content_hash,
        "condition": condition, "repeat": repeat, "protocol_hash": calls.protocol_hash,
        "model": calls.api.model, "service": calls.api.service, "executor": executor.identity,
        "shadow_only": True, "deployment_authorized": False, "hidden_feedback_used": False,
        **({"solver_profile": profile.to_dict()} if profile.enabled else {})})
    root = checked_path(root)
    # Reuse the existing local operation lock rather than creating a second
    # execution/cache implementation. No model or executor calls happen until
    # the structured-to-text mapping has been frozen successfully.
    with public_revision._revision_lock(root / "rule_solver"):
        path = root / "rule_exposure.json"
        if path.exists():
            require(public_revision._read(path) == mapping, "Position is bound to another rule exposure or history")
        else:
            require(not any((root / name).exists() for name in
                            ("artifacts", "public_initial", "public_revision", "rule_result.json")),
                    "Existing unbound solver outputs cannot acquire a new rule exposure")
            public_revision._write(path, mapping)
        initial = public_revision.solve_public_initial(public_row, text, condition, repeat, calls, root,
                                                      **profile.initial_options())
        revision = public_revision.revise_public(public_row, initial, text, calls, executor, root,
                                                **profile.revision_options())
        selected = revision["artifact"]
        require(initial.skill_hash == selected.skill_hash == text_hash,
                "Actual solver Skill text differs from frozen rule exposure")
        binding = seal({"version": VERSION, "exposure_hash": mapping["record_hash"],
            "initial_artifact_hash": initial.content_hash, "artifact_hash": selected.content_hash,
            "revision_hash": revision["record"]["record_hash"], "rule_skill_hash": skill.content_hash,
            "effective_skill_text_hash": text_hash, "shadow_only": True, "deployment_authorized": False,
            "fixture_only": calls.api.service.get("fixture") is True})
        public_revision._write(root / "rule_result.json", binding)
        return {"initial_artifact": initial, "artifact": selected, "revision": revision,
                "exposure": mapping, "record": binding}
