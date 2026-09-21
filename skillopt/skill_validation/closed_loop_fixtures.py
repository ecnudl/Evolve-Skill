"""Small, explicitly scripted ENGINEERING data for the gated-loop smoke.

These are neither natural model outputs nor held-out benchmark measurements.
Each partition has different task operations and identifiers, but the examples
are purpose-built illustrations and must not support a generalization claim.
Host labels describe these hand-written programs; they are NOT independent
executed audit measurements. Actual public checks must still run in a sandbox.
"""
from __future__ import annotations

import hashlib
import json

from skillopt.validator_pilot.api import digest

from .checks import CallableTask, PublicCase
from .models import ArtifactRecord, Obligation, SourceFile, TaskContract, require

VERSION = "gated-loop-engineering-fixtures-v1"
SCENARIOS = ("beneficial", "harmful", "insufficient")
PARENT_SKILL = """## Mechanism
Normalize collection order before calculating results.
## When
Use for every list-processing task.
## Procedure
Sort the caller's list in place, then calculate the requested result.
## Avoid
Avoid an unnecessary copy even when the task requires preserving inputs.
"""
CANDIDATE_SKILL = """## Mechanism
Preserve explicitly required caller-owned state while transforming a local view.
## When
Apply only when the public task explicitly requires input preservation.
## Procedure
Identify the required unchanged state. Work on a copied or non-mutating view.
Check the requested result and compare input state before and after execution
on legal nontrivial inputs, including an order different from the public example.
## Avoid
Do not impose preservation when mutation is permitted or required. Abstain
outside the explicit preservation condition; do not claim broad safe scope.
"""

# Explicit values, rather than using a hidden reference program to derive new
# visible test answers. The future reverse-list probe can check input state but
# is not entitled to invent an expected return using these host-only labels.
_VALUES = [-3, -1, 2, 4]
_OPERATIONS = (
    ("development", "development", "sort", "Return the integers in ascending order.",
     "ordered", [-3, -1, 2, 4]),
    ("verifier_calibration", "calibration", "sum", "Return the sum of the integers.",
     "sum(ordered)", 2),
    ("verifier_calibration", "calibration", "product", "Return the product of the integers.",
     "ordered[0] * ordered[1] * ordered[2] * ordered[3]", 24),
    ("verifier_calibration", "nonapplicable", "range", "Return the largest integer minus the smallest.",
     "ordered[-1] - ordered[0]", 7),
    ("verifier_calibration", "nonapplicable", "abs-total", "Return the sum of absolute integer values.",
     "sum(abs(value) for value in ordered)", 10),
    ("skill_confirmation", "target", "weighted-rank", "Return the sum of each sorted integer times its one-based rank.",
     "sum((index + 1) * value for index, value in enumerate(ordered))", 17),
    ("skill_confirmation", "target", "median-pair", "Return the middle two integers of the ascending four-element list.",
     "ordered[1:3]", [-1, 2]),
    ("skill_confirmation", "retention", "squares", "Return the squares of the integers in ascending input-value order.",
     "[value * value for value in ordered]", [9, 1, 4, 16]),
    ("skill_confirmation", "retention", "positive", "Return the positive integers in ascending order.",
     "[value for value in ordered if value > 0]", [2, 4]),
    ("skill_confirmation", "nonapplicable", "odd-count", "Return the count of odd integers.",
     "sum(value % 2 != 0 for value in ordered)", 2),
    ("skill_confirmation", "nonapplicable", "negative-total", "Return the sum of the negative integers.",
     "sum(value for value in ordered if value < 0)", -4),
    ("final", "target", "adjacent-gaps", "Return differences between consecutive integers in ascending order.",
     "[right - left for left, right in zip(ordered, ordered[1:])]", [2, 3, 2]),
    ("final", "retention", "pair-extremes", "Return a two-element list of the smallest and largest integers.",
     "[ordered[0], ordered[-1]]", [-3, 4]),
    ("final", "nonapplicable", "even-total", "Return the sum of even integers.",
     "sum(value for value in ordered if value % 2 == 0)", 6),
)


def _program(expression, *, mutating=False):
    setup = "    values.sort()\n    ordered = values\n" if mutating else "    ordered = sorted(values)\n"
    return "def solve(values):\n" + setup + "    return " + expression + "\n"


def fixture_tasks():
    """Return host rows; never serialize ``host_fixture`` to Research/updater.

    Frozen family IDs denote the explicit operations, not independent samples
    from a population. Their common list-processing scaffold remains a known
    source of dependence despite disjoint identifiers.
    """
    rows = []
    for partition, region, operation, requirement, expression, expected in _OPERATIONS:
        preserve = region != "nonapplicable"
        state_requirement = ("Do not mutate the input list." if preserve else
                             "Input mutation is permitted but is not required.")
        example = "Public example: arguments=" + json.dumps([_VALUES]) + "; expected return=" + json.dumps(expected) + "."
        prompt = " ".join((requirement, "The input is a list of four integers.",
                           "Input values may be in any order.", state_requirement, example))
        obligations = [Obligation("return", "requested_behavior", requirement, requirement)]
        if preserve:
            obligations.append(Obligation("input", "input_preservation", state_requirement, state_requirement))
        task_id = "closed-loop-fixture-" + operation
        task = CallableTask(TaskContract(
            task_id, task_id, "fixture-operation-" + operation, "fixture-project-" + operation,
            partition, "coding", "constraint_preservation", prompt, tuple(obligations)),
            "solution", "solve", (PublicCase(
                "public-sorted-example", json.dumps({"args": [_VALUES], "kwargs": {}}), example,
                tuple(obligation.id for obligation in obligations), json.dumps(expected)),))
        good, mutating = _program(expression), _program(expression, mutating=True)
        wrong = "def solve(values):\n    return None\n"
        codes = {"no_skill": good, "current": mutating if preserve else good, "candidate": good}
        labels = {"no_skill": {ob.id: "pass" for ob in obligations},
                  "current": {ob.id: "fail" if ob.id == "input" else "pass" for ob in obligations},
                  "candidate": {ob.id: "pass" for ob in obligations}}
        if region == "target":
            codes["no_skill"], labels["no_skill"]["return"] = wrong, "fail"
        if region == "retention":
            codes["current"], labels["current"] = good, {ob.id: "pass" for ob in obligations}
        if region == "nonapplicable" and partition != "verifier_calibration":
            # Forced use is harmful; pre-execution scope fallback must prevent it.
            codes["candidate"], labels["candidate"]["return"] = wrong, "fail"
        rows.append({"task": task, "region": region, "near_miss": not preserve,
                     "host_fixture": {"version": VERSION, "provenance_kind": "fixture",
                                      "codes": codes, "labels": labels, "mutating": mutating,
                                      "wrong": wrong, "labels_are_scripted_not_executed": True}})
    return rows


def _scenario_output(row, condition, scenario):
    require(scenario in SCENARIOS and condition in {"no_skill", "current", "candidate"},
            "Unknown fixture scenario/condition")
    fixture = row["host_fixture"]
    require(fixture["version"] == VERSION and fixture["provenance_kind"] == "fixture", "Explicit fixture metadata required")
    code, labels = fixture["codes"][condition], dict(fixture["labels"][condition])
    heldout = row["task"].contract.partition in {"skill_confirmation", "final"}
    if condition == "candidate" and heldout and scenario == "harmful" and row["region"] != "nonapplicable":
        if row["region"] == "target":
            code, labels["input"] = fixture["mutating"], "fail"
        else:
            code, labels["return"] = fixture["wrong"], "fail"
    if condition == "candidate" and heldout and scenario == "insufficient":
        code, labels = None, {ob.id: "unknown" for ob in row["task"].contract.obligations}
    return code, labels


def fixture_solver(row, *, condition, skill_text, repeat=0, scenario="beneficial"):
    """Scripted artifact producer; no LLM, network or execution is performed.

    The code is selected by the PREDECLARED scenario/condition, not generated
    from the Skill text. Thus even a passing loop is only an engineering smoke.
    """
    require(type(skill_text) is str and (condition != "no_skill" or skill_text == ""), "No-Skill must use empty text")
    code, _ = _scenario_output(row, condition, scenario)
    identity = {"version": VERSION, "task": row["task"].contract.content_hash,
                "condition": condition, "repeat": repeat, "scenario": scenario,
                "skill_hash": hashlib.sha256(skill_text.encode()).hexdigest(), "code": code}
    return ArtifactRecord(
        identity["task"], repeat, condition, "none" if condition == "no_skill" else "skill-" + identity["skill_hash"][:16],
        identity["skill_hash"], (SourceFile("solution.py", code),) if code is not None else (),
        "available" if code is not None else "parse_failure", "fixture", True, False,
        "synthetic:closed-loop:" + scenario + ":" + digest(identity), digest(identity))


def audit_labels(row, artifact):
    """HOST-ONLY predetermined labels, not a sandbox audit or research result.

    Reject arbitrary source/code substitutions rather than attaching good
    labels to an unrelated artifact with the same condition name.
    """
    require(type(artifact) is ArtifactRecord and artifact.provenance_kind == "fixture"
            and artifact.task_hash == row["task"].contract.content_hash, "Exact fixture artifact required")
    prefix = "synthetic:closed-loop:"
    require(artifact.source_ref.startswith(prefix), "Unknown fixture artifact source")
    scenario, separator, source_hash = artifact.source_ref[len(prefix):].partition(":")
    require(bool(separator), "Missing fixture source identity")
    code, labels = _scenario_output(row, artifact.condition, scenario)
    identity = {"version": VERSION, "task": row["task"].contract.content_hash,
                "condition": artifact.condition, "repeat": artifact.repeat, "scenario": scenario,
                "skill_hash": artifact.skill_hash, "code": code}
    require(digest(identity) == source_hash == artifact.source_hash
            and artifact.availability == ("available" if code is not None else "parse_failure")
            and artifact.files == ((SourceFile("solution.py", code),) if code is not None else ()),
            "Fixture audit cannot label changed code or source identity")
    return labels


def scripted_updater(system, user, max_output_tokens=None):
    """Return the scripted patch ONLY for a publicly observed paired regression.

    Input is the standard ``single_round_feedback.messages`` user JSON. This
    callback is a deterministic test double, not evidence that an LLM learned.
    A status word or proposed probe without observed before/after evidence is
    insufficient. Root orchestration must replay/bind receipts before this call.
    """
    del system, max_output_tokens
    payload = json.loads(user)

    def has_state(role, status, changed):
        for check in role.get("checks", ()):
            if check.get("method") != "input_state" or check.get("status") != status:
                continue
            for observation in check.get("observations", ()):
                required = {"before_args", "after_args", "before_kwargs", "after_kwargs"}
                if (observation.get("information_origin") != "recorded_public_execution"
                        or observation.get("status") != "observed" or not required <= set(observation)):
                    continue
                differs = (observation["before_args"] != observation["after_args"]
                           or observation["before_kwargs"] != observation["after_kwargs"])
                if differs is changed:
                    return True
        return False

    for pair in payload.get("feedback", {}).get("paired_development", ()):
        roles = pair.get("roles", {})
        if has_state(roles.get("current", {}), "fail", True) and has_state(roles.get("no_skill", {}), "pass", False):
            return CANDIDATE_SKILL
    return "NO_UPDATE"
