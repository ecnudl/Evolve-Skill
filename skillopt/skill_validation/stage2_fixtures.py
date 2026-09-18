"""Explicit engineering examples for the Stage-2 orchestration smoke.

No code is executed and no model/source is called here. Audit annotations are
hand-authored fixture labels, not independent research measurements. Different
operations occupy development/calibration/audit; repeats remain the same task
and must not count as new independent tasks or families.
"""
from __future__ import annotations

import hashlib
import json

from skillopt.validator_pilot.api import digest

from .checks import CallableTask, PublicCase
from .models import ArtifactRecord, Obligation, SourceFile, TaskContract
from .research import ModelReply

FIXTURE_SOURCE_URL = "https://docs.python.org/3.11/library/copy.html"
FIXTURE_QUOTE = (
    "Synthetic fixture guidance: compare input state before and after execution "
    "only when preservation is explicitly required by the task."
)
FIXTURE_SOURCE_TEXT = "ENGINEERING FIXTURE, NOT RETRIEVED DOCUMENTATION.\n" + FIXTURE_QUOTE

_OPERATIONS = (
    {
        "partition": "development", "family": "sorting",
        "return_requirement": "Return the input integers sorted in ascending order.",
        "ordinary_requirement": "Do not mutate the input list.",
        "inplace_requirement": "Sort the input list in place and return it.",
        "examples": (([[3, 1, 2]], [1, 2, 3]), ([[2, 2, 1]], [1, 2, 2])),
        "good": "def solve(values):\n    return sorted(values)\n",
        "mutating": "def solve(values):\n    values.sort()\n    return values\n",
    },
    {
        "partition": "verifier_calibration", "family": "stable-deduplication",
        "return_requirement": "Return the input integers without duplicates, retaining their first-occurrence order.",
        "ordinary_requirement": "Do not mutate the input list.",
        "inplace_requirement": "Remove duplicates from the input list in place and return that list.",
        "examples": (([[3, 1, 3, 2, 1]], [3, 1, 2]), ([[2, 2, 2]], [2])),
        "good": "def solve(values):\n    return list(dict.fromkeys(values))\n",
        "mutating": "def solve(values):\n    values[:] = list(dict.fromkeys(values))\n    return values\n",
    },
    {
        "partition": "verifier_audit", "family": "mapping-threshold-filter",
        "return_requirement": "Return a dictionary containing only entries whose integer value is at least the supplied threshold.",
        "ordinary_requirement": "Do not mutate the input dictionary.",
        "inplace_requirement": "Delete entries below the threshold from the input dictionary in place and return that dictionary.",
        "examples": (([{"a": 4, "b": -2, "c": 1}, 1], {"a": 4, "c": 1}),
                     ([{"a": 0, "b": 5}, 3], {"b": 5})),
        "good": "def solve(values, threshold):\n    return {key: value for key, value in values.items() if value >= threshold}\n",
        "mutating": "def solve(values, threshold):\n    for key in list(values):\n        if values[key] < threshold:\n            del values[key]\n    return values\n",
    },
)


def _task(operation, *, inplace):
    requirement = operation["inplace_requirement"] if inplace else operation["ordinary_requirement"]
    example_lines = []
    for arguments, expected in operation["examples"]:
        example_lines.append("Public example: arguments=" + json.dumps(arguments, sort_keys=True)
                             + "; expected return=" + json.dumps(expected, sort_keys=True) + ".")
    prompt = " ".join([operation["return_requirement"], requirement, *example_lines])
    obligations = [Obligation("return", "requested_behavior", operation["return_requirement"],
                              operation["return_requirement"])]
    if inplace:
        # This obligation remains visible and mandatory. No registered recipe
        # currently checks that the requested input mutation occurred, so no
        # public test is incorrectly assigned to it and its result stays unknown.
        obligations.append(Obligation("required_in_place", "requested_behavior", requirement, requirement))
    else:
        obligations.append(Obligation("input", "input_preservation", requirement, requirement))
    identifier = "stage2-fixture-" + operation["family"] + ("-in-place" if inplace else "-preserve")
    contract = TaskContract(
        identifier, identifier, "fixture-family-" + operation["family"],
        "fixture-project-" + operation["family"], operation["partition"], "coding",
        "constraint_preservation", prompt, tuple(obligations),
    )
    cases = tuple(PublicCase(
        id=f"example-{index}", arguments_json=json.dumps({"args": arguments, "kwargs": {}}, sort_keys=True),
        contract_quote=example_lines[index], obligation_ids=("return",) if inplace else ("return", "input"),
        expected_json=json.dumps(expected, sort_keys=True),
    ) for index, (arguments, expected) in enumerate(operation["examples"]))
    return CallableTask(contract, "solution", "solve", cases)


def _artifact(task, code, *, condition, repeat):
    skill_text = "" if condition == "no_skill" else "SYNTHETIC SKILL PLACEHOLDER: " + condition
    identity = {"fixture": "stage2", "task": task.contract.content_hash,
                "repeat": repeat, "condition": condition, "code_hash": digest(code)}
    return ArtifactRecord(
        task_hash=task.contract.content_hash, repeat=repeat, condition=condition,
        skill_version="none" if condition == "no_skill" else "fixture-" + condition + "-v1",
        skill_hash=hashlib.sha256(skill_text.encode()).hexdigest(), files=(SourceFile("solution.py", code),),
        availability="available", provenance_kind="fixture", provenance_complete=True, historical_only=False,
        source_ref="synthetic:stage2:" + digest(identity), source_hash=digest(identity),
    )


def fixture_pool() -> list[dict]:
    """Nine rows, 27 artifacts, three operation families; NOT natural runs.

    Per partition, repeat 0 encodes a Skill-induced regression and repeat 1 a
    Skill-associated repair of the *same* ordinary task. A separate in-place
    contract tests absence of a preservation obligation. Its mandatory mutation
    requirement is deliberately unknown, preventing a convenient false pass.
    """
    rows = []
    conditions = ("no_skill", "current", "candidate")
    for operation in _OPERATIONS:
        task = _task(operation, inplace=False)
        for repeat in (0, 1):
            codes = ((operation["good"], operation["good"], operation["mutating"]) if repeat == 0 else
                     (operation["mutating"], operation["mutating"], operation["good"]))
            artifacts = tuple(_artifact(task, code, condition=condition, repeat=repeat)
                              for condition, code in zip(conditions, codes))
            audit = {artifact.content_hash: {"return": "pass", "input": "pass" if code == operation["good"] else "fail"}
                     for artifact, code in zip(artifacts, codes)}
            rows.append({"task": task, "artifacts": artifacts, "audit": audit, "near_miss": False})
        task = _task(operation, inplace=True)
        artifacts = tuple(_artifact(task, operation["mutating"], condition=condition, repeat=0)
                          for condition in conditions)
        rows.append({"task": task, "artifacts": artifacts,
                     "audit": {artifact.content_hash: {"return": "pass", "required_in_place": "unknown"}
                               for artifact in artifacts}, "near_miss": True})
    return rows


def scripted_model(system, user, max_output_tokens) -> ModelReply:
    """Deterministic fixture callback. Zero provider tokens; no network.

    Both adaptive arms propose the same checks. No Research-exclusive gain is
    engineered. The Research fixture only exercises the source/citation path.
    """
    payload = json.loads(user)
    if "reflection" not in payload:
        response = {"status": "investigate", "questions": [
            "Which explicit input-preservation obligations lack state-comparison evidence, and when should this check not apply?"
        ], "urls": [FIXTURE_SOURCE_URL] if payload.get("approved_paths") else []}
    else:
        citations = []
        for source in payload.get("sources", []):
            if source.get("status") == "available" and FIXTURE_QUOTE in source.get("text", ""):
                citations = [{"source_id": source["source_id"], "quote": FIXTURE_QUOTE}]
                break
        response = {"status": "update", "reason": "Engineering fixture adds state evidence only for explicit preservation obligations.",
                    "rules": [
                        {"id": "public-return", "obligation_kind": "requested_behavior", "method": "public_examples",
                         "applicability": "explicit_obligation", "exception": "absent_obligation",
                         "evidence_requirement": "Execute host-registered public examples with public expected returns.",
                         "citations": [], "uncertainty": "Public examples do not establish all task behavior."},
                        {"id": "public-input-state", "obligation_kind": "input_preservation", "method": "input_state",
                         "applicability": "explicit_obligation", "exception": "absent_obligation",
                         "evidence_requirement": "Compare recorded input arguments before and after public-case execution.",
                         "citations": citations, "uncertainty": "Synthetic proposal; requires independent calibration, not a research result."},
                    ]}
    return ModelReply(response, input_tokens=0, output_tokens=0)


def scripted_fetcher(urls, root):
    """Synthetic source snapshots, explicitly marked in their visible text.

    The URL labels the approved destination that would be used by a real
    transport. It does NOT claim this text was fetched from Python documentation.
    """
    return [{"requested_url": url, "final_url": url, "ok": True,
             "text": FIXTURE_SOURCE_TEXT,
             "text_sha256": hashlib.sha256(FIXTURE_SOURCE_TEXT.encode()).hexdigest(),
             "retrieved_utc": "fixture-not-retrieved", "provenance_kind": "fixture"}
            for url in urls]
