"""Explicit timeout-repair fixtures; no model calls or source execution."""
import json
from copy import deepcopy

import pytest

from skillopt.skill_validation import public_revision as revision
from skillopt.validator_pilot.api import digest
from tests.test_skill_validation_public_revision import (
    REVISED,
    SECRET,
    FixtureCalls,
    FixtureExecutor,
    artifact,
    fixture_row,
)

PIN = "sha256:" + "a" * 64


class IsolatedFixture(FixtureExecutor):
    identity = {**FixtureExecutor.identity, "image": PIN, "timeout_seconds": 10}


def timeout(**changes):
    isolation = {"image": PIN, "timeout_seconds": 10, "network": "none", "root_read_only": True,
        "source_read_only": True, "user": "65534:65534", "cap_drop": ["ALL"],
        "no_new_privileges": True, "automatic_pull": False}
    return {"status": "execution_error", "reason": "execution_timeout", "actual": None,
        "exception": None, "cleanup_confirmed": True, "isolation": isolation,
        "isolation_hash": digest(isolation), "diagnostic": SECRET, **changes}


def run(root, *, response="KEEP", ok=True, outcomes=None, enabled=True):
    row = fixture_row()
    original = artifact(row)
    calls = FixtureCalls(response, ok=ok)
    executor = IsolatedFixture(*(outcomes if outcomes is not None else [timeout()]))
    result = revision.revise_public(row, original, "", calls, executor, root,
                                    allow_clean_timeout_revision=enabled)
    return result, row, original, calls, executor


def test_legacy_default_still_skips_timeout_without_new_policy_or_API(tmp_path):
    result, _, _, calls, executor = run(tmp_path, enabled=False)
    assert result["record"]["status"] == "skipped" and result["report"]["status"] == "unknown"
    assert "clean_timeout_revision_policy" not in result["record"]["request"]
    assert not calls.calls and len(executor.calls) == 1


def test_keep_after_clean_timeout_retains_unknown_and_has_public_whitelist(tmp_path):
    result, row, original, calls, executor = run(tmp_path)
    record = result["record"]
    assert record["status"] == "kept" and record["public_status"] == "unknown"
    assert result["artifact"] == original and record["retry_authorized"] is False
    assert record["request"]["clean_timeout_revision_policy"] == revision.CLEAN_TIMEOUT_POLICY
    request = calls.calls[0]
    assert SECRET not in request["system"] + request["user"]
    assert "not proof of an infinite loop" in request["system"]
    assert "infrastructure overhead" in request["system"]
    observation = json.loads(request["user"])["public_execution"]["observations"][0]
    assert observation["observation_status"] == "execution_budget_exceeded"
    assert observation["execution_budget_seconds"] == 10 and observation["semantic_outcome"] == "unknown"
    assert observation["observed"] is None and observation["exception"] is None
    assert len(executor.calls) == len(calls.calls) == 1
    assert revision.revise_public(row, original, "", calls, executor, tmp_path,
                                  allow_clean_timeout_revision=True) == result
    assert len(executor.calls) == len(calls.calls) == 1


def test_one_changed_revision_is_checked_but_never_receives_another_opportunity(tmp_path):
    result, row, original, calls, executor = run(tmp_path, response=json.dumps({"solution.py": REVISED}),
                                                outcomes=[timeout(), {"actual": True}])
    assert result["record"]["status"] == "revised" and result["report"]["status"] == "pass"
    assert result["record"]["draft_stage"]["report"]["status"] == "unknown"
    assert len(calls.calls) == 1 and len(executor.calls) == 2
    with pytest.raises(ValueError, match="second revision"):
        revision.revise_public(row, result["artifact"], "", calls, executor, tmp_path,
                              allow_clean_timeout_revision=True)
    assert revision.revise_public(row, original, "", calls, executor, tmp_path,
                                  allow_clean_timeout_revision=True) == result
    with pytest.raises(ValueError, match="intent changed"):
        revision.revise_public(row, original, "", calls, executor, tmp_path)


@pytest.mark.parametrize("response,ok,reason", [("invalid JSON", True, "parse_failure_no_retry"),
                                               (None, False, "api_failure_no_retry")])
def test_failed_revision_retains_unknown_no_retry(tmp_path, response, ok, reason):
    result, row, original, calls, executor = run(tmp_path, response=response, ok=ok)
    assert result["record"]["status"] == "fallback" and result["record"]["reason"] == reason
    assert result["report"]["status"] == "unknown" and result["artifact"] == original
    assert revision.revise_public(row, original, "", calls, executor, tmp_path,
                                  allow_clean_timeout_revision=True) == result
    assert len(calls.calls) == len(executor.calls) == 1


@pytest.mark.parametrize("changes", [
    {"status": "unsupported"}, {"reason": "executor_call_exception_no_retry"},
    {"reason": "ssh_stream_closed"}, {"reason": "execution_output_limit"},
    {"reason": "container_cleanup_unconfirmed"}, {"cleanup_confirmed": False},
    {"cleanup_confirmed": None}, {"exception": "MemoryError"}, {"exception": "TimeoutError"},
    {"actual": False}, {"isolation": {}}, {"isolation_hash": "0" * 64},
])
def test_other_unknown_or_unsafe_execution_never_opens_revision(tmp_path, changes):
    result, _, original, calls, _ = run(tmp_path, outcomes=[timeout(**changes)])
    assert result["record"]["status"] == "skipped" and result["artifact"] == original
    assert result["report"]["status"] == "unknown" and not calls.calls


@pytest.mark.parametrize("field,value", [("network", "host"), ("root_read_only", False),
    ("source_read_only", False), ("user", "0:0"), ("cap_drop", []),
    ("no_new_privileges", False), ("automatic_pull", True), ("timeout_seconds", True),
    ("timeout_seconds", 20), ("image", "python:latest")])
def test_bound_isolation_controls_are_required(tmp_path, field, value):
    outcome = timeout()
    outcome["isolation"][field] = value
    outcome["isolation_hash"] = digest(outcome["isolation"])
    result, _, _, calls, _ = run(tmp_path, outcomes=[outcome])
    assert result["record"]["status"] == "skipped" and not calls.calls


def test_mixed_timeout_and_infrastructure_unknown_is_not_eligible():
    good = {**timeout(), "executor_identity": IsolatedFixture.identity}
    stage = {"report": {"status": "unknown"}, "execution_records_host_only": [{"execution": good}]}
    assert revision._revision_eligible(stage, revision.CLEAN_TIMEOUT_POLICY)
    for bad in ({"status": "unsupported"}, {"status": "observed", "cleanup_confirmed": False},
                {"status": "observed", "cleanup_confirmed": True, "exception": "MemoryError"}):
        mixed = deepcopy(stage)
        mixed["execution_records_host_only"].append({"execution": bad})
        assert not revision._revision_eligible(mixed, revision.CLEAN_TIMEOUT_POLICY)


@pytest.mark.parametrize("seconds,image", [(10.5, PIN), (10.0, "example.org/python@" + PIN)])
def test_existing_executor_float_budget_and_named_pinned_image_are_supported(tmp_path, seconds, image):
    outcome = timeout()
    outcome["isolation"].update(timeout_seconds=seconds, image=image)
    outcome["isolation_hash"] = digest(outcome["isolation"])
    executor = IsolatedFixture(outcome)
    executor.identity = {**executor.identity, "timeout_seconds": seconds, "image": image}
    row, calls = fixture_row(), FixtureCalls()
    result = revision.revise_public(row, artifact(row), "", calls, executor, tmp_path,
                                    allow_clean_timeout_revision=True)
    assert result["record"]["status"] == "kept" and result["report"]["status"] == "unknown"
    assert len(calls.calls) == 1


@pytest.mark.parametrize("seconds", [float("nan"), float("inf"), -float("inf"), True, 0, -1, 121])
def test_invalid_budget_never_counts_as_clean_timeout(seconds):
    outcome = timeout()
    outcome["isolation"]["timeout_seconds"] = seconds
    outcome["isolation_hash"] = digest(outcome["isolation"])
    outcome["executor_identity"] = {**IsolatedFixture.identity, "timeout_seconds": seconds}
    assert not revision._clean_timeout(outcome)


def test_default_and_enabled_observed_path_messages_are_byte_identical(tmp_path):
    default, _, _, left, _ = run(tmp_path / "legacy", outcomes=[{"actual": True}], enabled=False)
    enabled, _, _, right, _ = run(tmp_path / "new", outcomes=[{"actual": True}])
    assert left.calls == right.calls
    assert default["record"]["public_status"] == enabled["record"]["public_status"] == "pass"


def test_resealed_timeout_report_cannot_invent_execution_eligibility(tmp_path):
    from tests.test_skill_validation_public_revision import reseal
    result, row, original, calls, executor = run(tmp_path)
    record = deepcopy(result["record"])
    execution = record["draft_stage"]["execution_records_host_only"][0]
    execution["execution"]["cleanup_confirmed"] = False
    execution["execution"] = reseal(execution["execution"])
    changed_hash = execution["record_hash"]
    record["draft_stage"]["execution_records_host_only"][0] = reseal(execution)
    new_hash = record["draft_stage"]["execution_records_host_only"][0]["record_hash"]
    report = record["draft_stage"]["report"]
    for check in report["checks"]:
        check["evidence_refs"] = [new_hash if x == changed_hash else x for x in check["evidence_refs"]]
    record["draft_stage"]["report"] = reseal(report)
    record["draft_stage"] = reseal(record["draft_stage"])
    terminal = tmp_path / "public_revision" / original.content_hash / "record.json"
    terminal.write_text(json.dumps(reseal(record)))
    with pytest.raises(ValueError, match="eligible public execution"):
        revision.revise_public(row, original, "", calls, executor, tmp_path,
                              allow_clean_timeout_revision=True)
    assert len(calls.calls) == len(executor.calls) == 1


@pytest.mark.parametrize("value", [None, "yes", 1, [], {}])
def test_opt_in_requires_exact_boolean_before_calls(tmp_path, value):
    with pytest.raises(ValueError, match="boolean"):
        run(tmp_path, enabled=value)
