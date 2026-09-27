"""Offline receipt fixtures for the annex adapter, never method-effect evidence."""
import json
from copy import deepcopy
from dataclasses import replace

import pytest

from skillopt.coevolution_v5.core import seal, verify
from skillopt.skill_validation.checks import ExecutionCache, pipeline_hash, validate_callable
from skillopt.skill_validation.development_feedback import build_development_feedback
from skillopt.skill_validation.mechanism_case_feedback import (
    ANNEX_POLICY, ARMS, CALL_KIND, PromptBudgetExceeded, _CASE_FIELDS,
    _share_pair_observations, build_request, collect_details, propose,
)
from skillopt.skill_validation import public_case_feedback
from skillopt.skill_validation.mechanism_learning import build_request as mechanism_request
from skillopt.skill_validation.research import fixed_rubric
from skillopt.skill_validation.rule_learning import build_update_request, candidate_from_response
from skillopt.skill_validation.rule_skill import RuleSkill, render_skill
from skillopt.validator_pilot.api import digest
from tests.test_skill_validation_public_revision import (
    FixtureCalls, FixtureExecutor, SECRET, artifact, fixture_row, reseal,
)
from tests.test_skill_validation_rule_learning import response


def source(*, repeats=1, detail_limit=10, availability="available"):
    parent, row, executor = RuleSkill("fixture-parent", ()), fixture_row(), FixtureExecutor()
    # Keep the fixture's semantic IDs/host labels private but give it ordinary
    # wrapper source; the original boolean bundle intentionally shows source.
    row["public_wrapper"] = {"path": "public_runner.py", "content": "# registered fixture public checker"}
    cache, entries = ExecutionCache(executor), []
    for repeat in range(repeats):
        artifacts = tuple(artifact(row, condition=role, repeat=repeat, availability=availability)
                          for role in ("no_skill", "current"))
        reports = tuple(validate_callable(row["public_task"], a, fixed_rubric(), cache) for a in artifacts)
        entries.append({"task": row["public_task"], "artifacts": artifacts, "reports": reports})
    bundle = build_development_feedback(entries, parent_skill=render_skill(parent), rubric=fixed_rubric(),
        pipeline_hash=pipeline_hash(fixed_rubric(), cache), execution_identity=cache.identity,
        execution_records=tuple(cache.records.values()), detail_limit=detail_limit)
    return parent, bundle, row


def collect_fixture(tmp_path, **options):
    parent, bundle, row = source(**options)
    executor = FixtureExecutor(*({"actual": 3} for _ in range(32)))
    details = collect_details(parent, bundle, [row], executor, tmp_path / "annex")
    return parent, bundle, row, executor, details


def expand_pair(pair):
    """Test-only inverse: reconstruct the full v1-shaped role observations."""
    result = {}
    for role, value in pair["roles"].items():
        if "observations_ref" in value:
            assert value["observations_ref"] == "shared_observations"
            result[role] = {"public_case_record_hash": value["public_case_record_hash"],
                            **deepcopy(pair["shared_observations"])}
        else:
            result[role] = deepcopy(value)
    return result


def test_only_existing_selected_details_are_executed_and_source_identity_is_retained(tmp_path):
    parent, bundle, row, executor, details = collect_fixture(tmp_path, repeats=3, detail_limit=1)
    verify(details)
    assert len(details["entries"]) == len(details["sources"]) == 1
    assert len(executor.calls) == 2  # One selected pair, not all three repeat pairs.
    assert all(call["module"] == "solution" and call["args"] == [[1, 2]] for call in executor.calls)
    source_row = details["sources"][0]
    assert source_row["task_hash"] == row["task"].contract.content_hash
    assert source_row["public_task_hash"] == row["public_task"].content_hash
    assert source_row["evidence_id"] in {e["id"] for e in build_update_request(parent, bundle)["evidence_catalog"]}
    for role, record in details["entries"][0]["roles"].items():
        assert record["artifact"]["condition"] == role
        assert record["artifact"]["repeat"] == source_row["repeat"]
        assert record["request"]["artifact_record_hash"] == source_row["artifacts"][role]
    assert details["parent_hash"] == parent.content_hash
    assert details["feedback_bundle_hash"] == bundle["record_hash"]
    assert not details["research_increment"] and not details["learning_authorized"]


def test_identical_visible_pairs_can_share_id_without_losing_repeat_bindings(tmp_path):
    parent, bundle, _, executor, details = collect_fixture(tmp_path, repeats=2)
    assert len(details["entries"]) == 2 and len(executor.calls) == 4
    assert len({s["evidence_id"] for s in details["sources"]}) == 1
    assert {s["repeat"] for s in details["sources"]} == {0, 1}
    request = build_request(parent, bundle, details, arm="case_details")
    annex = json.loads(request["user"])["public_case_annex"]
    assert [p["pair_index"] for p in annex] == [0, 1]


def test_control_changes_only_annex_and_keeps_original_boolean_feedback(tmp_path):
    parent, bundle, _, _, details = collect_fixture(tmp_path)
    requests = [build_request(parent, bundle, details, arm=arm) for arm in ARMS]
    left, right = requests
    base = mechanism_request(parent, bundle, strategy="mechanism")
    assert left["system"] == right["system"] == base["system"] + ANNEX_POLICY
    assert left["max_tokens"] == right["max_tokens"] == 2048
    assert left["max_edits"] == right["max_edits"] == 2
    assert left["evidence_catalog"] == right["evidence_catalog"] == base["evidence_catalog"]
    assert left["parser_request_hash"] == right["parser_request_hash"] == base["parser_request_hash"]
    lu, ru = json.loads(left["user"]), json.loads(right["user"])
    assert lu.pop("public_case_annex") == []
    annex = ru.pop("public_case_annex")
    assert lu == ru == json.loads(base["user"])
    assert annex[0]["evidence_id"] == lu["feedback"]["paired_development"][0]["evidence_id"]
    assert all(role["status"] == "pass" for role in lu["feedback"]["paired_development"][0]["roles"].values())
    assert left["base_user_hash"] == right["base_user_hash"] == digest(base["user"])
    for request in requests:
        assert request["prompt_hash"] == digest({"system": request["system"], "user": request["user"]})


def test_annex_omits_repeated_source_and_private_ids_but_retains_unknowns(tmp_path):
    parent, bundle, _, _, details = collect_fixture(tmp_path, availability="api_failure")
    request = build_request(parent, bundle, details, arm="case_details")
    annex = json.loads(request["user"])["public_case_annex"]
    raw = json.dumps(annex)
    assert SECRET not in raw
    for field in ("task_hash", "artifact_record_hash", "task", "artifact", "source_ref", "host_only", "contract_quote"):
        assert json.dumps(field) + ":" not in raw
    for role in expand_pair(annex[0]).values():
        assert role["public_case_record_hash"]
        assert len(role["cases"]) == 1
        assert role["cases"][0]["return_check"]["status"] == "unknown"
        assert role["cases"][0]["other_state_requirements"]["status"] == "unknown"


def test_existing_wrapper_failure_is_not_overridden_by_direct_return_pass(tmp_path):
    parent, bundle, row = source()
    # Build a genuinely replay-valid failed wrapper bundle, not a changed label.
    executor = FixtureExecutor({"actual": False}, {"actual": False})
    cache = ExecutionCache(executor)
    artifacts = tuple(artifact(row, condition=role) for role in ("no_skill", "current"))
    reports = tuple(validate_callable(row["public_task"], a, fixed_rubric(), cache) for a in artifacts)
    bundle = build_development_feedback([{"task": row["public_task"], "artifacts": artifacts, "reports": reports}],
        parent_skill="", rubric=fixed_rubric(), pipeline_hash=pipeline_hash(fixed_rubric(), cache),
        execution_identity=cache.identity, execution_records=tuple(cache.records.values()))
    details = collect_details(parent, bundle, [row], FixtureExecutor({"actual": 3}, {"actual": 3}), tmp_path / "details")
    payload = json.loads(build_request(parent, bundle, details, arm="case_details")["user"])
    assert all(r["status"] == "fail" for r in payload["feedback"]["paired_development"][0]["roles"].values())
    assert all(r["cases"][0]["return_check"]["status"] == "pass"
               for r in expand_pair(payload["public_case_annex"][0]).values())


def test_equal_observations_share_losslessly_but_keep_both_receipts_and_host_records(tmp_path):
    parent, bundle, _, _, details = collect_fixture(tmp_path, repeats=2)
    original = deepcopy(details)
    request = build_request(parent, bundle, details, arm="case_details")
    assert request["version"] == details["version"] == "same-feedback-public-case-annex-v2"
    annex = json.loads(request["user"])["public_case_annex"]
    assert len(annex) == len(details["entries"]) == 2  # No sharing between repeat/task pairs.
    for pair, entry in zip(annex, details["entries"]):
        assert "shared_observations" in pair
        full = expand_pair(pair)
        for role, record in entry["roles"].items():
            view = public_case_feedback.model_view(record)
            expected = {"public_case_record_hash": record["record_hash"],
                        "cases": [{k: case[k] for k in _CASE_FIELDS} for case in view["cases"]],
                        "counts": view["counts"]}
            assert full[role] == expected
            assert pair["roles"][role] == {"public_case_record_hash": record["record_hash"],
                                          "observations_ref": "shared_observations"}
        assert full["no_skill"]["public_case_record_hash"] != full["current"]["public_case_record_hash"]
    assert details == original
    assert "independent evidence" in ANNEX_POLICY


def test_unequal_actual_observations_remain_separate_in_full(tmp_path):
    parent, bundle, row = source()
    executor = FixtureExecutor({"actual": 3}, {"actual": 4})
    details = collect_details(parent, bundle, [row], executor, tmp_path / "different")
    pair = json.loads(build_request(parent, bundle, details, arm="case_details")["user"])["public_case_annex"][0]
    assert "shared_observations" not in pair
    assert all("cases" in value and "counts" in value and "observations_ref" not in value
               for value in pair["roles"].values())
    assert pair["roles"]["no_skill"]["cases"][0]["return_check"]["status"] == "pass"
    assert pair["roles"]["current"]["cases"][0]["return_check"]["status"] == "fail"


@pytest.mark.parametrize("change", ["boolean_vs_int", "different_count", "unknown_vs_fail", "input_order"])
def test_sharing_compares_all_typed_cases_and_counts_not_receipt_ids(change):
    observations = {"cases": [{"actual": True, "input": [1, 2], "status": "unknown"}],
                    "counts": {"unknown": 1}}
    roles = {role: {"public_case_record_hash": digest(role), **deepcopy(observations)}
             for role in ("no_skill", "current")}
    assert "shared_observations" in _share_pair_observations(roles)
    if change == "boolean_vs_int":
        roles["current"]["cases"][0]["actual"] = 1
    elif change == "different_count":
        roles["current"]["counts"]["unknown"] = 2
    elif change == "unknown_vs_fail":
        roles["current"]["cases"][0]["status"] = "fail"
    else:
        roles["current"]["cases"][0]["input"] = [2, 1]
    assert _share_pair_observations(roles) == {"roles": roles}


def test_unknown_observations_can_share_without_becoming_failures_or_losing_cases(tmp_path):
    parent, bundle, _, _, details = collect_fixture(tmp_path, availability="api_failure")
    pair = json.loads(build_request(parent, bundle, details, arm="case_details")["user"])["public_case_annex"][0]
    assert "shared_observations" in pair
    full = expand_pair(pair)
    assert len(full["no_skill"]["cases"]) == len(full["current"]["cases"]) == 1
    assert all(value["cases"][0]["return_check"]["status"] == "unknown" for value in full.values())
    assert len({value["public_case_record_hash"] for value in full.values()}) == 2


def test_old_v1_details_cannot_acquire_v2_authority_by_replay(tmp_path):
    parent, bundle, _, _, details = collect_fixture(tmp_path)
    old = reseal({**details, "version": "same-feedback-public-case-annex-v1"})
    with pytest.raises(ValueError, match="fields/version"):
        build_request(parent, bundle, old, arm="case_details")


def test_repeat_collection_replays_terminal_cases_without_execution(tmp_path):
    parent, bundle, row, executor, details = collect_fixture(tmp_path)
    assert collect_details(parent, bundle, [row], executor, tmp_path / "annex") == details
    assert len(executor.calls) == 2


@pytest.mark.parametrize("change", ["missing", "duplicate", "different_checker"])
def test_unbound_panel_rows_fail_before_execution(tmp_path, change):
    parent, bundle, row = source()
    rows = [] if change == "missing" else [row, row] if change == "duplicate" else [
        {"task": row["task"], "public_task": replace(row["public_task"], function="other"),
         "public_wrapper": row["public_wrapper"]}]
    executor = FixtureExecutor()
    with pytest.raises(ValueError):
        collect_details(parent, bundle, rows, executor, tmp_path)
    assert not executor.calls


def test_changed_direct_registration_cannot_resume_same_annex_directory(tmp_path):
    parent, bundle, row, executor, _ = collect_fixture(tmp_path)
    task = row["task"]
    row["task"] = replace(task, public_cases=(replace(task.public_cases[0], expected_json="99"),))
    with pytest.raises(ValueError):
        collect_details(parent, bundle, [row], executor, tmp_path / "annex")
    assert len(executor.calls) == 2


def test_different_runtime_is_rejected_before_execution(tmp_path):
    parent, bundle, row = source()
    class DifferentExecutor(FixtureExecutor):
        identity = {"kind": "different-fixture", "real_execution": False}
    executor = DifferentExecutor()
    with pytest.raises(ValueError, match="executor policy"):
        collect_details(parent, bundle, [row], executor, tmp_path)
    assert not executor.calls


@pytest.mark.parametrize("change", ["parent", "bundle", "source", "role", "repeat", "derived", "missing_case", "extra_field"])
def test_annex_resealing_cannot_rebind_source_or_forge_observations(tmp_path, change):
    parent, bundle, _, _, details = collect_fixture(tmp_path)
    details = deepcopy(details)
    if change == "parent":
        details["parent_hash"] = digest("other-parent")
    elif change == "bundle":
        details["feedback_bundle_hash"] = digest("other-bundle")
    elif change == "source":
        details["entries"][0]["source"]["evidence_id"] = "ev_invented"
    elif change == "role":
        roles = details["entries"][0]["roles"]
        roles["current"] = roles["no_skill"]
    elif change == "repeat":
        details["entries"][0]["source"]["repeat"] += 1
    elif change in {"derived", "missing_case"}:
        record = details["entries"][0]["roles"]["current"]
        if change == "derived":
            record["cases"][0]["return_check"]["status"] = "fail"
        else:
            record["execution_records"] = []
        details["entries"][0]["roles"]["current"] = reseal(record)
    else:
        details["private_audit"] = SECRET
    with pytest.raises(ValueError):
        build_request(parent, bundle, reseal(details), arm="case_details")


@pytest.mark.parametrize("arm", ARMS)
def test_proposal_uses_original_parser_and_separately_binds_actual_annex_prompt(tmp_path, arm):
    parent, bundle, _, _, details = collect_fixture(tmp_path)
    raw = response(parent, bundle)
    calls = FixtureCalls(raw)
    result = propose(calls, parent, bundle, details, arm=arm, repeat=2)
    verify(result)
    update = verify(result["update"])
    assert len(calls.calls) == 1 and calls.calls[0]["max_tokens"] == 2048
    assert calls.calls[0]["kind"] == CALL_KIND and calls.calls[0]["repeat"] == 2
    assert result["status"] == update["status"] == "candidate"
    assert update["candidate"] == candidate_from_response(raw, parent, bundle)["candidate"]
    assert update["actual_update_request_hash"] == result["request"]["record_hash"]
    assert update["parser_request_hash"] == build_update_request(parent, bundle)["record_hash"]
    assert update["parser_request_hash"] != update["actual_update_request_hash"]
    assert result["api_receipt"]["response"] == raw and result["fixture_only"]
    assert not update["semantic_support_verified"] and not update["learning_authorized"]
    assert not update["deployment_authorized"] and not update["research_increment"]


def test_case_record_hash_is_not_a_new_permitted_rule_evidence_id(tmp_path):
    parent, bundle, _, _, details = collect_fixture(tmp_path)
    parsed = json.loads(response(parent, bundle))
    new_id = details["entries"][0]["roles"]["current"]["record_hash"]
    parsed["edits"][0]["evidence_ids"] = [new_id]
    parsed["edits"][0]["rule"]["evidence_ids"] = [new_id]
    result = propose(FixtureCalls(json.dumps(parsed)), parent, bundle, details, arm="case_details")
    assert result["update"]["status"] == "invalid" and result["update"]["candidate"] is None


@pytest.mark.parametrize("ok,response_value,status", [(False, "", "api_failure"),
    (True, "NO_UPDATE", "no_update"), (True, "broken", "invalid")])
def test_non_candidate_results_are_preserved_without_retry(tmp_path, ok, response_value, status):
    parent, bundle, _, _, details = collect_fixture(tmp_path)
    calls = FixtureCalls(response_value, ok=ok)
    result = propose(calls, parent, bundle, details, arm="case_details")
    assert result["status"] == result["update"]["status"] == status
    assert result["update"]["candidate"] is None and len(calls.calls) == 1
    assert not result["retry_authorized"]


@pytest.mark.parametrize("bad", ["missing", "different", "exception"])
def test_missing_or_wrong_receipt_never_becomes_no_update(tmp_path, bad):
    parent, bundle, _, _, details = collect_fixture(tmp_path)
    class BrokenCalls(FixtureCalls):
        def call(self, *args, **kwargs):
            value = super().call(*args, **kwargs)
            if bad == "exception":
                raise RuntimeError("Interrupted no retry")
            if bad == "missing":
                del value["request"]
            else:
                value["request"]["user"] = "different evidence"
                value["request_hash"] = digest(value["request"])
            return value
    calls = BrokenCalls("NO_UPDATE")
    with pytest.raises((ValueError, RuntimeError)):
        propose(calls, parent, bundle, details, arm="case_details")
    assert len(calls.calls) == 1


def test_oversized_prompt_refuses_instead_of_dropping_unknowns_or_feedback(tmp_path, monkeypatch):
    from skillopt.skill_validation import mechanism_case_feedback as module
    parent, bundle, _, _, details = collect_fixture(tmp_path)
    request = build_request(parent, bundle, details, arm="case_details")
    expected_size = len((request["system"] + request["user"]).encode("utf-8"))
    monkeypatch.setattr(module, "MAX_PROMPT_BYTES", 1)
    calls = FixtureCalls("NO_UPDATE")
    with pytest.raises(PromptBudgetExceeded, match="do not truncate") as caught:
        propose(calls, parent, bundle, details, arm="case_details")
    assert caught.value.actual_bytes == expected_size and caught.value.limit_bytes == 1
    assert not calls.calls


def test_integrity_error_is_not_misclassified_as_prompt_budget(tmp_path):
    parent, bundle, _, _, details = collect_fixture(tmp_path)
    changed = reseal({**details, "parent_hash": digest("wrong-parent")})
    with pytest.raises(ValueError) as caught:
        build_request(parent, bundle, changed, arm="case_details")
    assert not isinstance(caught.value, PromptBudgetExceeded)


@pytest.mark.parametrize("options", [{"arm": "bad"}, {"arm": None},
    {"arm": "boolean", "repeat": True}, {"arm": "case_details", "max_tokens": 2049}])
def test_invalid_options_fail_before_api(tmp_path, options):
    parent, bundle, _, _, details = collect_fixture(tmp_path)
    calls = FixtureCalls("NO_UPDATE")
    with pytest.raises(ValueError):
        propose(calls, parent, bundle, details, **options)
    assert not calls.calls
