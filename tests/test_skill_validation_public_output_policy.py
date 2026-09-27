"""Budget/format protocol fixtures: no model, network or candidate execution."""
import json
from copy import deepcopy

import pytest

from skillopt.skill_validation import public_revision as revision
from skillopt.validator_pilot.api import digest
from tests.test_skill_validation_clean_timeout_revision import IsolatedFixture, timeout
from tests.test_skill_validation_public_revision import (
    CODE,
    REVISED,
    SECRET,
    FixtureCalls,
    FixtureExecutor,
    artifact,
    fixture_row,
    reseal,
)

OPTIONS = {"max_tokens": 4096, "format_policy": revision.COMPACT_JSON_POLICY}


def initial_record(root, draft):
    return revision._read(root / "public_initial" / (draft.content_hash + ".json"))


def test_default_initial_messages_and_record_shape_are_legacy(tmp_path):
    row, calls = fixture_row(), FixtureCalls(json.dumps({"solution.py": CODE}))
    expected_system = (
        "Solve the public Python programming task. Return ONLY a valid JSON object mapping exactly "
        "'solution.py' to its complete Python source string, including necessary imports. "
        "Implement the requested signature; escape newlines and quotes within JSON. "
        "No Markdown fences. You have at most one later revision opportunity after actual public "
        "checks when those checks are available and unambiguous. No hidden audit feedback is available. "
        + revision._SAFETY)
    expected_user = json.dumps({"task": row["task"].contract.prompt, "optional_skill": ""},
                               ensure_ascii=False, sort_keys=True)
    assert revision._initial_messages(row["task"], "") == (expected_system, expected_user)
    draft = revision.solve_public_initial(row, "", "no_skill", 2, calls, tmp_path)
    record = initial_record(tmp_path, draft)
    assert calls.calls[0]["max_tokens"] == 2048
    assert calls.calls[0]["system"] == expected_system and calls.calls[0]["user"] == expected_user
    assert "max_tokens" not in record and "format_policy" not in record
    assert set(record) == {"version", "stage", "artifact_record_hash", "artifact_hash", "api_receipt",
                          "information_origin", "hidden_feedback_used", "fixture_only", "formal_effect_estimate",
                          "record_hash"}


@pytest.mark.parametrize("condition,skill", [("no_skill", ""), ("current", "Parent"), ("candidate", "Candidate")])
def test_initial_4096_compact_is_bound_and_projects_public_fields_only(tmp_path, condition, skill):
    row, calls = fixture_row(), FixtureCalls(json.dumps({"solution.py": CODE}))
    draft = revision.solve_public_initial(row, skill, condition, 2, calls, tmp_path, **OPTIONS)
    record = initial_record(tmp_path, draft)
    assert draft.availability == "available" and record["max_tokens"] == 4096
    assert record["format_policy"] == revision.COMPACT_JSON_POLICY
    system, user = revision._initial_messages(row["task"], skill, format_policy=record["format_policy"])
    revision._receipt(record["api_receipt"], system, user, "public-initial", 2, max_tokens=record["max_tokens"])
    assert draft.source_hash == digest(record["api_receipt"])
    assert revision.COMPACT_JSON_POLICY in system and "complete source string" in system
    assert SECRET not in system + user
    assert set(json.loads(user)) == {"task", "optional_skill"}
    assert "response_format" not in calls.calls[0]
    assert len(calls.calls) == 1
    for cap, policy in [(2048, revision.COMPACT_JSON_POLICY), (4096, None)]:
        bad_system, bad_user = revision._initial_messages(row["task"], skill, format_policy=policy)
        with pytest.raises(ValueError, match="receipt belongs"):
            revision._receipt(record["api_receipt"], bad_system, bad_user, "public-initial", 2, max_tokens=cap)


@pytest.mark.parametrize("cap", [1, 2048, 4096, 16000])
@pytest.mark.parametrize("policy", [None, revision.COMPACT_JSON_POLICY])
def test_revision_output_options_replay_without_added_calls(tmp_path, cap, policy):
    row, calls, executor = fixture_row(), FixtureCalls("KEEP"), FixtureExecutor()
    original = artifact(row)
    options = {"max_tokens": cap, "format_policy": policy}
    result = revision.revise_public(row, original, "", calls, executor, tmp_path, **options)
    request = result["record"]["request"]
    assert {k: request[k] for k in ("max_tokens", "format_policy") if k in request} == revision._output_options(cap, policy)
    assert calls.calls[0]["max_tokens"] == cap
    assert (revision.COMPACT_JSON_POLICY in calls.calls[0]["system"]) == (policy is not None)
    if policy is not None:
        assert "KEEP is also allowed" in calls.calls[0]["system"]
    assert SECRET not in calls.calls[0]["system"] + calls.calls[0]["user"]
    assert revision.revise_public(row, original, "", calls, executor, tmp_path, **options) == result
    assert len(calls.calls) == len(executor.calls) == 1


@pytest.mark.parametrize("options", [
    {"max_tokens": True}, {"max_tokens": False}, {"max_tokens": 0}, {"max_tokens": -1},
    {"max_tokens": 16001}, {"max_tokens": 4096.0}, {"max_tokens": "4096"}, {"max_tokens": None},
    {"format_policy": "unknown"}, {"format_policy": {}}, {"format_policy": []}, {"format_policy": True},
])
def test_invalid_options_fail_before_any_call_or_file(tmp_path, options):
    row, calls, executor = fixture_row(), FixtureCalls(), FixtureExecutor()
    with pytest.raises(ValueError):
        revision.solve_public_initial(row, "", "no_skill", 0, calls, tmp_path / "initial", **options)
    with pytest.raises(ValueError):
        revision.revise_public(row, artifact(row), "", calls, executor, tmp_path / "revision", **options)
    assert not calls.calls and not executor.calls and not list(tmp_path.iterdir())


@pytest.mark.parametrize("changed", [{"max_tokens": 8192, "format_policy": revision.COMPACT_JSON_POLICY},
                                    {"max_tokens": 4096}, {}])
def test_cannot_change_output_protocol_while_resuming_one_revision(tmp_path, changed):
    row, calls, executor = fixture_row(), FixtureCalls(), FixtureExecutor()
    original = artifact(row)
    revision.revise_public(row, original, "", calls, executor, tmp_path, **OPTIONS)
    with pytest.raises(ValueError, match="intent changed"):
        revision.revise_public(row, original, "", calls, executor, tmp_path, **changed)
    assert len(calls.calls) == len(executor.calls) == 1


@pytest.mark.parametrize("field,value", [("max_tokens", 8192), ("max_tokens", 2048),
                                        ("format_policy", None), ("format_policy", "other")])
def test_resealed_revision_cannot_relabel_receipt_budget_or_format(tmp_path, field, value):
    row, calls, executor = fixture_row(), FixtureCalls(), FixtureExecutor()
    original = artifact(row)
    result = revision.revise_public(row, original, "", calls, executor, tmp_path, **OPTIONS)
    bad = deepcopy(result["record"])
    bad["request"][field] = value
    bad = reseal(bad)
    with pytest.raises(ValueError):
        revision._result(bad, bad["request"], original, row["task"], row["public_task"], "", executor)


def test_receipt_rejects_boolean_budget_even_when_equal_to_one():
    calls = FixtureCalls()
    receipt = calls.call("system", "user", "public-initial", repeat=0, max_tokens=True)
    with pytest.raises(ValueError, match="receipt belongs"):
        revision._receipt(receipt, "system", "user", "public-initial", 0, max_tokens=1)


@pytest.mark.parametrize("response,ok,availability", [
    ('{"solution.py":"def solve(values):', True, "parse_failure"),
    ('{"solution.py":"def solve(values):', False, "api_failure"),
    (json.dumps({"solution.py": CODE}) + " commentary", True, "parse_failure"),
    ("```json\n" + json.dumps({"solution.py": CODE}) + "\n```", True, "available"),
])
def test_compact_policy_does_not_salvage_partial_outputs_or_change_parser(tmp_path, response, ok, availability):
    row, calls = fixture_row(), FixtureCalls(response, ok=ok)
    draft = revision.solve_public_initial(row, "", "no_skill", 0, calls, tmp_path, **OPTIONS)
    assert draft.availability == availability and len(calls.calls) == 1
    assert initial_record(tmp_path, draft)["api_receipt"]["response"] == response


@pytest.mark.parametrize("first,second,expected", [
    ({"actual": True}, {"actual": False}, "retained"),
    ({"actual": True}, timeout(), "retained"),
    (timeout(), {"actual": True}, "revised"),
])
def test_compact_cap_interacts_with_timeout_and_nonregression_once(tmp_path, first, second, expected):
    row, calls = fixture_row(), FixtureCalls(json.dumps({"solution.py": REVISED}))
    executor, original = IsolatedFixture(first, second), artifact(row)
    options = {**OPTIONS, "allow_clean_timeout_revision": True,
               "public_selection_policy": revision.PUBLIC_NONREGRESSION_POLICY}
    result = revision.revise_public(row, original, "", calls, executor, tmp_path, **options)
    assert result["record"]["status"] == expected
    assert result["record"]["revised_artifact"] is not None  # Rejected attempts are never erased.
    assert result["record"]["revision_opportunity_completed"]
    assert result["record"]["retry_authorized"] is False
    assert len(calls.calls) == 1 and len(executor.calls) == 2
    assert calls.calls[0]["max_tokens"] == 4096 and revision.COMPACT_JSON_POLICY in calls.calls[0]["system"]
    assert revision.revise_public(row, original, "", calls, executor, tmp_path, **options) == result
    assert len(calls.calls) == 1 and len(executor.calls) == 2
