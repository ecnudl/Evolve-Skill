"""Explicit synthetic records for engineering smoke, never model runs."""
from __future__ import annotations

import hashlib

from skillopt.validator_pilot.api import digest

from .models import ArtifactRecord, EvidenceRecord, Obligation, Observation, SourceFile, TaskContract


def smoke_cases():
    for name in ("preserved", "changed", "unavailable", "in_place"):
        inplace = name == "in_place"
        prompt = "Return the sorted values. " + ("Modify the input list in place." if inplace else "Do not mutate input data.")
        obligations = [Obligation("requested", "requested_behavior", "Return the sorted values.", "Return the sorted values.")]
        if not inplace:
            obligations.append(Obligation("input", "input_preservation", "Do not mutate input data.", "Do not mutate input data."))
        else:
            obligations.append(Obligation("required_in_place", "requested_behavior", "Modify the input list in place.",
                                          "Modify the input list in place."))
        task = TaskContract(
            "fixture-" + name, "fixture-" + name, "fixture-sorting", "synthetic-smoke", "development",
            "coding", "constraint_preservation", prompt, tuple(obligations),
        )
        artifact = ArtifactRecord(
            task_hash=task.content_hash, repeat=0, condition="no_skill", skill_version="none",
            skill_hash=hashlib.sha256(b"").hexdigest(),
            files=(SourceFile("solution.py", "def solve(values):\n    values.sort()\n    return values\n"
                              if name in {"changed", "in_place"} else "def solve(values):\n    return sorted(values)\n"),),
            availability="available", provenance_kind="fixture", provenance_complete=True,
            historical_only=False, source_ref="synthetic:" + name, source_hash=digest({"fixture": name}),
        )
        observations = [Observation("return_0", "requested", "public_test", passed=True)]
        if inplace:
            observations.append(Observation("required_in_place_0", "required_in_place", "public_test", passed=True))
        if not inplace:
            observations.append(Observation("state_0", "input", "input_state",
                                            before_hash=digest([2, 1]),
                                            after_hash=digest([1, 2] if name == "changed" else [2, 1])))
        evidence = EvidenceRecord(
            task_hash=task.content_hash, artifact_hash=artifact.artifact_hash, artifact_record_hash=artifact.content_hash,
            repeat=0, visibility="public", execution_status="unsupported" if name == "unavailable" else "observed",
            observations=() if name == "unavailable" else tuple(observations),
            source_ref="synthetic-public-receipt:" + name, source_hash=digest({"fixture_receipt": name}),
            provenance_kind="fixture",
        )
        yield name, task, artifact, (evidence,)
