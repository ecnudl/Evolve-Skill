"""Offline cold-start rule-learning wiring, exclusively scripted fixtures.

No model, Research, sandbox, H, eval, or generated-code execution is invoked.
The two cold conditions have identical empty Skill text: their deliberately
different scripted outputs illustrate feedback plumbing, not a Skill effect.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from copy import deepcopy
from pathlib import Path

from skillopt.coevolution_v5.core import seal
from skillopt.validator_pilot.api import digest, write_immutable_json

from .checks import CallableTask, ExecutionCache, PublicCase, pipeline_hash, validate_callable
from .development_feedback import build_development_feedback
from .models import ArtifactRecord, Obligation, RubricCheck, RubricVersion, SourceFile, TaskContract, require
from .rule_learning import build_update_request, candidate_from_response
from .rule_skill import RuleEdit, RuleSkill, RuleUpdate, apply_update, render_for_task, render_skill
from .skill_seed import cold_seed, seed_model_text

VERSION = "conditional-rule-learning-offline-smoke-v1"
PROVENANCE = "fixture_no_research_effect_not_natural"
_GOOD = "def solve(values):\n    return sum(values)\n"
_MUTATING = "def solve(values):\n    values.sort()\n    return sum(values)\n"


class _ScriptedExecutor:
    """Only create marked fixture receipts for two exact handwritten programs."""

    identity = {"fixture_executor": VERSION, "real_execution": False}

    def run(self, files, module, function, args, kwargs):
        require(files in ({"solution.py": _GOOD}, {"solution.py": _MUTATING})
                and module == "solution" and function == "solve"
                and args == [[2, 1]] and kwargs == {}, "Unsupported smoke fixture invocation")
        call = {"module": module, "function": function, "args": args, "kwargs": kwargs}
        return seal({"status": "observed", "actual": 3, "exception": None,
                     "before_args": deepcopy(args),
                     "after_args": [[1, 2]] if files["solution.py"] == _MUTATING else deepcopy(args),
                     "before_kwargs": {}, "after_kwargs": {},
                     "input_hash": digest({"files": files, **call}), "source_hash": digest(files),
                     "call_hash": digest(call), "executor_identity": self.identity,
                     "fixture_only": True, "evidence_provenance": PROVENANCE})


def _task(name, *, preserve=True):
    requirement = "Return the sum of the integer list."
    state = "Do not modify the input list." if preserve else "Sort the input list in place before returning."
    example = "Public example: solve([2, 1]) returns 3."
    obligations = (Obligation("return", "requested_behavior", requirement, requirement),)
    if preserve:
        obligations += (Obligation("input", "input_preservation", state, state),)
    task = TaskContract("rule-smoke-" + name, "rule-smoke-" + name, "fixture-family-" + name,
        "fixture-rule-project", "development", "coding", "constraint_preservation",
        " ".join((requirement, state, example)), obligations)
    case = PublicCase("public", '{"args":[[2,1]],"kwargs":{}}', example,
                      tuple(o.id for o in obligations), expected_json="3")
    return CallableTask(task, "solution", "solve", (case,))


def _fixture_feedback(parent):
    rubric = RubricVersion("rule-smoke-public", "constraint_preservation", "registered-public-cases",
        "stage2-contract-checks-v1", "explicit-contract", "common-obligations",
        (RubricCheck("returns", "requested_behavior", "public_examples", "explicit_obligation",
                     "absent_obligation", "scripted public fixture receipt"),
         RubricCheck("preserves", "input_preservation", "input_state", "explicit_obligation",
                     "absent_obligation", "scripted before/after fixture receipt")))
    cache, entries = ExecutionCache(_ScriptedExecutor(), max_executions=4), []
    for index, task in enumerate((_task("preservation"), _task("unavailable"))):
        artifacts = []
        for condition in ("no_skill", "current"):
            available = not (index == 1 and condition == "current")
            code = _MUTATING if condition == "current" else _GOOD
            text = "" if condition == "no_skill" else render_skill(parent)
            artifacts.append(ArtifactRecord(task.contract.content_hash, 0, condition, "fixture-cold",
                hashlib.sha256(text.encode()).hexdigest(), (SourceFile("solution.py", code),) if available else (),
                "available" if available else "parse_failure", "fixture", True, False,
                "fixture:rule-learning-smoke", digest([VERSION, index, condition])))
        artifacts = tuple(artifacts)
        reports = tuple(validate_callable(task, artifact, rubric, cache) for artifact in artifacts)
        entries.append({"task": task, "artifacts": artifacts, "reports": reports})
    bundle = build_development_feedback(entries, parent_skill=render_skill(parent), rubric=rubric,
        pipeline_hash=pipeline_hash(rubric, cache), execution_identity=cache.identity,
        execution_records=tuple(cache.records.values()))
    return bundle, cache.new_executions


def run(output):
    """Write deterministic fixture artifacts; never overwrite different outputs."""
    root = Path(output).absolute()
    require(not any(p.is_symlink() for p in (root, *root.parents)), "Symlink smoke output is unsupported")
    seed = cold_seed("fixture-cold-0")
    parent = RuleSkill.from_dict(seed["structured_skill"])
    require(seed_model_text(seed) == "", "Cold fixture must start without learned content")
    bundle, fixture_calls = _fixture_feedback(parent)
    requests = {mode: build_update_request(parent, bundle, update_mode=mode, engineering_simulation=True)
                for mode in ("rule_patch", "whole_text")}
    require(requests["rule_patch"]["feedback_view_hash"] == requests["whole_text"]["feedback_view_hash"],
            "Update controls must share exactly the same public feedback")
    public_pairs = json.loads(requests["rule_patch"]["user"])["feedback"]["paired_development"]
    evidence_id = next(item["id"] for item in requests["rule_patch"]["evidence_catalog"]
                       if public_pairs[item["location"][1]]["roles"]["current"]["status"] == "fail")
    proposal = {"parent_hash": parent.content_hash, "edits": [{"operation": "add", "rule_id": "preserve_input",
        "rule": {"id": "preserve_input", "mechanism": "constraint_preservation",
                 "procedure": ["Identify explicitly preserved caller-owned inputs before choosing a transformation.",
                               "Use a non-mutating view and compare input state around available public checks."],
                 "when": "The task explicitly requires the caller-owned input to remain unchanged.",
                 "exceptions": ["Do not impose this rule when the task permits or requires mutation."],
                 "scope": {"required_obligation_kinds": ["input_preservation"], "forbidden_obligation_kinds": []},
                 "evidence_ids": [evidence_id]},
        "evidence_ids": [evidence_id], "reason": "Scripted illustration of an explicitly required input-state check."}]}
    response = json.dumps(proposal, sort_keys=True)
    candidate = candidate_from_response(response, parent, bundle, engineering_simulation=True)
    require(candidate["status"] == "candidate", "Scripted valid rule proposal was not parsed")
    skill = RuleSkill.from_dict(candidate["candidate"])
    rendering = seal({"provenance": PROVENANCE,
        "applicable": render_for_task(skill, _task("preservation")),
        "near_miss": render_for_task(skill, _task("in-place", preserve=False)),
        "semantic_applicability_verified": False, "deployment_authorized": False})
    # Structural edge-case only: this is not a second training round and has no
    # new feedback, confirmation, or claim that removing the rule is beneficial.
    removed = apply_update(skill, RuleUpdate(skill.content_hash,
        (RuleEdit("remove", "preserve_input", None, (evidence_id,), "Fixture-only deletion roundtrip."),)))
    no_update = candidate_from_response("NO_UPDATE", parent, bundle, engineering_simulation=True)
    whole_text = """## Mechanism
Preserve explicitly required caller-owned state.
## When
The task requires unchanged input.
## Procedure
Choose non-mutating operations and inspect before/after state with public checks.
## Avoid
Do not impose preservation when mutation is permitted or required.
"""
    whole_candidate = candidate_from_response(whole_text, parent, bundle, update_mode="whole_text",
                                              engineering_simulation=True)
    edges = seal({"provenance": PROVENANCE, "no_update": no_update,
                  "deletion_format_roundtrip": removed.to_dict(), "deleted_text": render_skill(removed.skill),
                  "deletion_is_not_a_second_learning_round": True, "deployment_authorized": False})
    files = {"seed.json": seed, "feedback.json": bundle,
             "update_requests.json": seal({"provenance": PROVENANCE, "requests": requests}),
             "model_views.json": seal({"provenance": PROVENANCE, "views": {
                 mode: {"system": request["system"], "user": request["user"]} for mode, request in requests.items()}}),
             "proposal.json": seal({"provenance": PROVENANCE, "scripted_response": response}),
             "candidate.json": candidate, "whole_text_candidate.json": whole_candidate,
             "rendering.json": rendering, "edge_cases.json": edges}
    summary = seal({"version": VERSION, "provenance": PROVENANCE,
        "api_calls": 0, "research_calls": 0, "real_executions": 0, "hidden_audit_reads": 0,
        "scripted_receipt_calls": fixture_calls, "feedback_coverage": bundle["coverage"],
        "cold_rule_count": len(parent.rules), "candidate_rule_count": len(skill.rules),
        "same_feedback_between_update_modes": True, "candidate_status": candidate["status"],
        "near_miss_disabled": rendering["near_miss"]["text"] == "", "deletion_returns_empty": edges["deleted_text"] == "",
        "deployment_authorized": False, "method_effect_evaluated": False,
        "artifacts": {name: item["record_hash"] for name, item in sorted(files.items())},
        "limitations": ["All task outputs and updates are handwritten engineering fixtures, not model experiments.",
                        "The two cold arms contain the same empty Skill; scripted differences are not causal Skill effects.",
                        "No Verifier Gate or Skill Gate has authorized feedback or deployment.",
                        "Kind-based Near-Miss filtering does not prove natural-language applicability or generalization."]})
    files["summary.json"] = summary
    # Validate the complete destination before writing anything, including when
    # resuming a partial run. A historical/non-smoke directory is never reused.
    if root.exists():
        require(root.is_dir() and {p.name for p in root.iterdir()} <= set(files), "Output contains unrelated historical files")
    for name, value in files.items():
        path = root / name
        require(not path.is_symlink(), "Symlink smoke artifact is unsupported")
        if path.exists():
            require(path.is_file() and json.loads(path.read_text()) == value,
                    "Immutable smoke artifact differs; choose a new output directory")
    for name, value in files.items():
        write_immutable_json(root / name, value)
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    print(json.dumps(run(args.output), ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
