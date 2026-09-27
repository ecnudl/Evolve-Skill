"""Public-only selection controls: fabricated observations, no API or execution."""
import json
from copy import deepcopy

import pytest

from skillopt.skill_validation import public_revision as revision
from tests.test_skill_validation_clean_timeout_revision import IsolatedFixture, timeout
from tests.test_skill_validation_public_revision import (
    REVISED,
    SECRET,
    FixtureCalls,
    artifact,
    fixture_row,
    reseal,
)


def run(root, before=True, after=False, *, policy=revision.PUBLIC_NONREGRESSION_POLICY,
        clean_timeout=False, response=None, ok=True):
    row = fixture_row()
    draft = artifact(row)
    calls = FixtureCalls(json.dumps({"solution.py": REVISED}) if response is None else response, ok=ok)
    executor = IsolatedFixture(before if isinstance(before, dict) else {"actual": before},
                               after if isinstance(after, dict) else {"actual": after})
    result = revision.revise_public(row, draft, "", calls, executor, root,
        allow_clean_timeout_revision=clean_timeout, public_selection_policy=policy)
    return result, row, draft, calls, executor


@pytest.mark.parametrize("after,expected", [(False, "fail"), (timeout(), "unknown")])
def test_public_pass_keeps_original_after_bad_or_unknown_attempt(tmp_path, after, expected):
    result, row, draft, calls, executor = run(tmp_path, after=after)
    record = result["record"]
    assert record["status"] == "retained" and result["artifact"] == draft
    assert record["reason"] == "public_nonregression_revised_" + expected
    assert record["public_status"] == result["report"]["status"] == "pass"
    assert record["revised_stage"]["report"]["status"] == expected
    assert record["revised_artifact"] is not None and record["api_receipt"] is not None
    assert record["revised_artifact_hash"] != record["selected_artifact_hash"]
    assert record["revision_opportunity_completed"] is True and record["retry_authorized"] is False
    assert len(calls.calls) == 1 and len(executor.calls) == 2
    assert SECRET not in calls.calls[0]["system"] + calls.calls[0]["user"]
    assert revision.revise_public(row, draft, "", calls, executor, tmp_path,
        public_selection_policy=revision.PUBLIC_NONREGRESSION_POLICY) == result
    assert len(calls.calls) == 1 and len(executor.calls) == 2


@pytest.mark.parametrize("before,after", [(False, True), (True, True), (False, False)])
def test_other_known_transitions_still_select_single_attempt(tmp_path, before, after):
    result, _, draft, calls, executor = run(tmp_path, before, after)
    assert result["record"]["status"] == "revised" and result["artifact"] != draft
    assert result["record"]["reason"] == "single_revision_selected"
    assert result["record"]["revision_opportunity_completed"]
    assert len(calls.calls) == 1 and len(executor.calls) == 2


def test_clean_timeout_and_selection_policies_combine_without_unknown_as_fail(tmp_path):
    result, row, draft, calls, executor = run(tmp_path, before=timeout(), after=True, clean_timeout=True)
    record = result["record"]
    assert record["status"] == "revised" and result["artifact"] != draft
    assert record["draft_stage"]["report"]["status"] == "unknown"
    assert record["public_status"] == "pass"
    assert record["request"]["clean_timeout_revision_policy"] == revision.CLEAN_TIMEOUT_POLICY
    assert record["request"]["public_selection_policy"] == revision.PUBLIC_NONREGRESSION_POLICY
    observation = json.loads(calls.calls[0]["user"])["public_execution"]["observations"][0]
    assert observation["semantic_outcome"] == "unknown"
    assert revision.revise_public(row, draft, "", calls, executor, tmp_path,
        allow_clean_timeout_revision=True, public_selection_policy=revision.PUBLIC_NONREGRESSION_POLICY) == result


def test_legacy_default_selects_failed_revision_and_model_messages_are_unchanged(tmp_path):
    old, _, old_draft, old_calls, _ = run(tmp_path / "old", policy=None)
    new, _, new_draft, new_calls, _ = run(tmp_path / "new")
    assert old["record"]["status"] == "revised" and old["artifact"] != old_draft
    assert old["report"]["status"] == "fail"
    assert "public_selection_policy" not in old["record"]["request"]
    assert new["record"]["status"] == "retained" and new["artifact"] == new_draft
    assert old_calls.calls == new_calls.calls


def test_policy_cannot_be_changed_on_existing_position(tmp_path):
    _, row, draft, calls, executor = run(tmp_path)
    with pytest.raises(ValueError, match="intent changed"):
        revision.revise_public(row, draft, "", calls, executor, tmp_path)
    assert len(calls.calls) == 1 and len(executor.calls) == 2


@pytest.mark.parametrize("change", ["reason", "select_attempt", "absent_policy", "unused_opportunity"])
def test_resealed_selection_tampering_is_rejected(tmp_path, change):
    result, row, draft, _, executor = run(tmp_path)
    record = deepcopy(result["record"])
    if change == "reason":
        record["reason"] = "public_nonregression_revised_unknown"
    elif change == "select_attempt":
        record.update(status="revised", reason="single_revision_selected",
                      selected_artifact=record["revised_artifact"],
                      selected_artifact_hash=record["revised_artifact_hash"],
                      selected_source_hash=record["revised_source_hash"], public_status="fail")
    elif change == "absent_policy":
        record["request"].pop("public_selection_policy")
    else:
        record["revision_opportunity_completed"] = False
    record = reseal(record)
    with pytest.raises(ValueError, match="public-only policy|explicit public nonregression|consumed revision"):
        revision._result(record, record["request"], draft, row["task"], row["public_task"], "", executor)


@pytest.mark.parametrize("decision,reason,erase_receipt", [
    ("fallback", "api_failure_no_retry", False), ("fallback", "parse_failure_no_retry", False),
    ("skipped", "public_execution_unknown_or_unsupported", False),
    ("skipped", "public_execution_unknown_or_unsupported", True), ("kept", "explicit_keep", False),
])
def test_attempt_cannot_be_erased_from_new_policy_replay(tmp_path, decision, reason, erase_receipt):
    result, row, draft, _, executor = run(tmp_path)
    record = deepcopy(result["record"])
    record.update(status=decision, reason=reason, revised_artifact=None, revised_stage=None,
                  revised_artifact_hash=None, revised_source_hash=None,
                  revision_opportunity_completed=decision == "kept")
    if erase_receipt:
        record["api_receipt"] = None
    record = reseal(record)
    with pytest.raises(ValueError, match="preserve every parseable|erase an eligible"):
        revision._result(record, record["request"], draft, row["task"], row["public_task"], "", executor)


@pytest.mark.parametrize("policy", [True, False, 1, [], {}, "unknown-policy"])
def test_policy_validation_before_any_execution(tmp_path, policy):
    with pytest.raises(ValueError, match="Unsupported public selection"):
        run(tmp_path, policy=policy)
    assert not (tmp_path / "public_revision").exists()


@pytest.mark.parametrize("response,ok,status", [("KEEP", True, "kept"), ("bad JSON", True, "fallback"),
                                              ("", False, "fallback")])
def test_no_valid_attempt_keeps_existing_outcomes(tmp_path, response, ok, status):
    result, _, draft, calls, executor = run(tmp_path, response=response, ok=ok)
    assert result["record"]["status"] == status and result["artifact"] == draft
    assert result["record"]["revised_artifact"] is None and result["record"]["revised_stage"] is None
    assert len(calls.calls) == len(executor.calls) == 1


@pytest.mark.parametrize("unknown_after", [False, True])
def test_rejected_attempt_is_exposed_to_feedback_not_hidden_by_selected_pass(tmp_path, monkeypatch, unknown_after):
    from skillopt.skill_validation.public_repair_feedback import build_details, build_request
    from tests import test_skill_validation_public_repair_feedback as feedback_tests

    class SelectionFixture(IsolatedFixture):
        def __init__(self, *outcomes, **kwargs):
            # The source helper's empty executor is the later final-artifact
            # public recheck; selected originals pass in this control.
            self.final_recheck = not outcomes
            if len(outcomes) > 1 and unknown_after:
                outcomes = (outcomes[0], timeout())
            super().__init__(*outcomes, **kwargs)

        def run(self, *args, **kwargs):
            if self.final_recheck:
                self.outcomes = [{"actual": True}]
            return super().run(*args, **kwargs)

    original = revision.revise_public

    def revise(*args, **kwargs):
        return original(*args, **kwargs, public_selection_policy=revision.PUBLIC_NONREGRESSION_POLICY,
                        allow_clean_timeout_revision=True)

    monkeypatch.setattr(revision, "revise_public", revise)
    monkeypatch.setattr(feedback_tests, "FixtureExecutor", SelectionFixture)
    parent, bundle, sources, _ = feedback_tests.fixture_source(tmp_path, ("deteriorated",))
    details = build_details(parent, bundle, sources)
    expected = "unknown" if unknown_after else "deteriorated"
    assert details["coverage"]["deduplicated_transition_counts"] == {"stable": 1}
    assert details["coverage"]["deduplicated_attempt_transition_counts"] == {expected: 1}
    item = details["annex"][0]["shared_trajectory"]
    assert item["revision_decision"] == "retained" and item["source_changed"] is False
    assert item["selected_public_check"]["status"] == "pass"
    assert item["attempt_transition"] == expected
    attempted = item["attempted_revision"]
    assert attempted["solution.py"] == REVISED and attempted["selected"] is False
    assert attempted["source_changed_from_draft"] is True
    assert attempted["public_check"]["status"] == ("unknown" if unknown_after else "fail")
    if unknown_after:
        observation = attempted["public_check"]["observations"][0]
        assert observation["observation_status"] == "execution_budget_exceeded"
        assert observation["semantic_outcome"] == "unknown"
    left, right = [build_request(parent, bundle, details, arm=arm) for arm in ("summary_only", "trajectory")]
    assert left["system"] == right["system"] and left["evidence_catalog"] == right["evidence_catalog"]
    luser, ruser = json.loads(left["user"]), json.loads(right["user"])
    assert luser.pop("public_repair_annex") == []
    assert ruser.pop("public_repair_annex")[0]["shared_trajectory"]["attempted_revision"] == attempted
    assert luser == ruser and SECRET not in right["system"] + right["user"]


def test_attempted_deterioration_has_detail_priority_under_new_policy():
    from skillopt.skill_validation.public_repair_feedback import _select
    ordinary = {"transition": "stable", "final_feedback_status": "pass", "public_recheck_disagreement": False}
    retained = {**ordinary, "attempt_transition": "deteriorated",
                "public_selection_policy": revision.PUBLIC_NONREGRESSION_POLICY}
    pairs = {("a", 0): {"no_skill": ordinary, "current": ordinary},
             ("b", 0): {"no_skill": retained, "current": retained}}
    assert _select(pairs, {k: k[0] for k in pairs}, 1) == [("b", 0)]
