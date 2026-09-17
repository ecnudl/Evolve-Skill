"""Independent boundary tests using explicit fixtures, never natural outputs."""

import hashlib
import json
import subprocess
from dataclasses import replace

import pytest

from skillopt.skill_validation.engine import validate
from skillopt.skill_validation.models import (
    ArtifactRecord,
    EvidenceRecord,
    Obligation,
    Observation,
    SourceFile,
    TaskContract,
)
from skillopt.skill_validation.views import bind, verifier_view
from skillopt.validator_pilot.api import CachedAPI, digest


def fixture_task(**changes):
    values = dict(
        task_id="fixture:host-task", original_task_id="fixture:original",
        family_id="fixture:host-family", project_id="fixture:project",
        partition="development", domain="coding", mechanism="HOST_MECHANISM",
        prompt="Return the supplied value.",
        obligations=(Obligation("host-obligation", "requested_behavior", "Return the supplied value.",
                                "Return the supplied value."),),
        public_files=(SourceFile("solution.py", "def solve(value): return value\n"),),
    )
    return TaskContract(**(values | changes))


def fixture_artifact(task, **changes):
    values = dict(
        task_hash=task.content_hash, repeat=0, condition="no_skill",
        skill_version="HOST_NO_SKILL", skill_hash=hashlib.sha256(b"").hexdigest(),
        files=task.public_files, availability="available", provenance_kind="fixture",
        provenance_complete=True, historical_only=False,
        source_ref="HOST_ONLY_SOURCE", source_hash=digest("fixture-source"),
    )
    return ArtifactRecord(**(values | changes))


def fixture_evidence(task, artifact, **changes):
    values = dict(
        task_hash=task.content_hash, artifact_hash=artifact.artifact_hash,
        artifact_record_hash=artifact.content_hash, repeat=artifact.repeat,
        visibility="public", execution_status="observed",
        observations=(Observation("HOST_OBSERVATION", "host-obligation", "public_test", passed=True),),
        source_ref="HOST_EXECUTION_SOURCE", source_hash=digest("fixture-execution"),
        provenance_kind="fixture",
    )
    return EvidenceRecord(**(values | changes))


@pytest.mark.parametrize("changes", [
    {"condition": "candidate", "skill_version": "candidate-v1", "skill_hash": digest("skill")},
    {"source_ref": "another-run", "source_hash": digest("another-run")},
])
def test_identical_artifact_receipt_cannot_be_swapped_between_runs(changes):
    task = fixture_task()
    first = fixture_artifact(task)
    other = replace(first, **changes)
    receipt = fixture_evidence(task, first)
    assert first.artifact_hash == other.artifact_hash
    assert first.content_hash != other.content_hash
    bind(task, first, (receipt,))
    with pytest.raises(ValueError, match="mismatch|another|record|run"):
        bind(task, other, (receipt,))
    # Legitimate separately bound equal-content outputs remain blindly comparable.
    other_receipt = fixture_evidence(task, other, source_hash=digest("another-execution"))
    assert verifier_view(task, first, (receipt,)) == verifier_view(task, other, (other_receipt,))


def test_host_annotations_and_partition_do_not_change_blind_input():
    first_task = fixture_task()
    first = fixture_artifact(first_task)
    first_receipt = fixture_evidence(first_task, first)
    other_task = replace(first_task, task_id="hidden:other-task", original_task_id="hidden:source",
                         family_id="hidden:family", project_id="hidden:project",
                         mechanism="hidden:near_miss", partition="verifier_audit")
    other = fixture_artifact(other_task)
    other_receipt = fixture_evidence(other_task, other)
    assert verifier_view(first_task, first, (first_receipt,)) == verifier_view(other_task, other, (other_receipt,))
    visible = json.dumps(verifier_view(first_task, first, (first_receipt,)))
    for marker in ("HOST_MECHANISM", "HOST_NO_SKILL", "HOST_ONLY_SOURCE", "HOST_EXECUTION_SOURCE",
                   "HOST_OBSERVATION", "host-obligation", "fixture:host-family"):
        assert marker not in visible


@pytest.mark.parametrize("failure", ["api_failure", "parse_failure"])
def test_missing_delivery_is_unknown_not_semantic_failure(failure):
    task = fixture_task()
    artifact = fixture_artifact(task, availability=failure, files=())
    receipt = fixture_evidence(task, artifact, execution_status=failure, observations=())
    report = validate(task, artifact, (receipt,))
    assert report.status == "unknown"
    assert report.obligation_results == (("host-obligation", "unknown"),)
    assert not any(check.status == "fail" for check in report.checks)


@pytest.mark.parametrize("failure", ["unsupported", "execution_error"])
def test_partial_execution_unknown_is_retained_despite_another_pass(failure):
    task = fixture_task()
    artifact = fixture_artifact(task)
    good = fixture_evidence(task, artifact)
    unavailable = fixture_evidence(task, artifact, execution_status=failure, observations=(),
                                   source_hash=digest(failure))
    report = validate(task, artifact, (good, unavailable))
    assert report.status == "unknown"
    assert not any(check.status == "fail" for check in report.checks)


def test_confirmed_failure_is_not_erased_by_other_unknown_execution():
    task = fixture_task()
    artifact = fixture_artifact(task)
    bad = fixture_evidence(task, artifact,
                           observations=(Observation("failed", "host-obligation", "public_test", passed=False),))
    unavailable = fixture_evidence(task, artifact, execution_status="unsupported", observations=(),
                                   source_hash=digest("unavailable"))
    assert validate(task, artifact, (bad, unavailable)).status == "fail"


def test_same_source_receipt_cannot_be_relabelled_as_independent_execution():
    task = fixture_task()
    artifact = fixture_artifact(task)
    receipt = fixture_evidence(task, artifact)
    aliased = replace(receipt, source_ref="a-second-name-for-same-receipt")
    with pytest.raises(ValueError, match="relabeled|receipt"):
        bind(task, artifact, (receipt, aliased))


def test_nested_payload_cannot_bypass_typed_public_view():
    with pytest.raises(ValueError, match="text|payload"):
        fixture_task(prompt={"text": "Public", "hidden_test": "PRIVATE_SENTINEL"})
    with pytest.raises(ValueError, match="text|payload"):
        SourceFile("solution.py", {"source": "pass", "audit": "PRIVATE_SENTINEL"})
    task = fixture_task()
    artifact = fixture_artifact(task)
    receipt = fixture_evidence(task, artifact)
    nested = receipt.to_dict()
    nested["observations"][0]["hidden_test"] = "PRIVATE_SENTINEL"
    with pytest.raises(ValueError, match="fields"):
        EvidenceRecord.from_dict(nested)
    with pytest.raises(ValueError, match="fields"):
        ArtifactRecord.from_dict(artifact.to_dict() | {"audit_truth": True})


def test_replay_never_invokes_a_client_or_executes_candidate(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Offline replay invoked an API client or subprocess")

    monkeypatch.setattr(CachedAPI, "__init__", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    task = fixture_task()
    artifact = fixture_artifact(task, files=(SourceFile("solution.py", "raise RuntimeError('MUST_NOT_EXECUTE')\n"),))
    # There is deliberately no observation claiming this fixture has executed.
    assert validate(task, artifact, ()).status == "unknown"


def test_serialized_records_are_detached_and_preserve_binding():
    task = fixture_task()
    artifact = fixture_artifact(task)
    receipt = fixture_evidence(task, artifact)
    payload = json.loads(json.dumps(receipt.to_dict()))
    assert EvidenceRecord.from_dict(payload) == receipt
    payload["observations"][0]["passed"] = False
    assert receipt.observations[0].passed is True
    assert EvidenceRecord.from_dict(payload).content_hash != receipt.content_hash
