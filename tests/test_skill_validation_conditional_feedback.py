"""Conditional updater boundary tests; scripted receipts, no API or execution."""
import json
from copy import deepcopy
from dataclasses import replace

import pytest

from skillopt.skill_validation.checks import ExecutionCache, pipeline_hash, validate_callable
from skillopt.skill_validation.conditional_feedback import (
    PUBLIC_CONTEXT,
    deterministic_select,
    messages,
    public_role_summary,
)
from skillopt.skill_validation.single_round_feedback import build_feedback_bundle, parse_update
from skillopt.validator_pilot.api import digest
from tests.test_skill_validation_checks import ScriptedExecutor
from tests.test_skill_validation_single_round_feedback import CANDIDATE, PARENT, _bundle, _inputs, _reseal


def _entries(count=64):
    original = _inputs()[0][0]
    entries = []
    for index in range(count):
        contract = replace(original["task"].contract, task_id=f"public-task-{index}",
                           prompt=original["task"].contract.prompt + f" Public task variant {index}.")
        task = replace(original["task"], contract=contract)
        artifacts = tuple(replace(artifact, task_hash=task.contract.content_hash) for artifact in original["artifacts"])
        # Selection does not use reports; only the later bundle builder may
        # validate or project them. These are deliberately not rebound reports.
        entries.append({"task": task, "artifacts": artifacts, "reports": original["reports"]})
    return entries


def _keys(entries):
    return [(entry["task"].contract.content_hash, entry["artifacts"][0].repeat) for entry in entries]


def _multi_bundle(count=20):
    entries = _entries(count)
    _, options = _inputs()
    cache = ExecutionCache(ScriptedExecutor())
    for entry in entries:
        entry["reports"] = tuple(validate_callable(entry["task"], artifact, options["rubric"], cache)
                                 for artifact in entry["artifacts"])
    options.update(pipeline_hash=pipeline_hash(options["rubric"], cache), execution_identity=cache.identity,
                   execution_records=tuple(cache.records.values()))
    return entries, build_feedback_bundle(entries, **options)


def test_selection_is_frozen_task_hash_order_and_bounded_to_sixteen():
    entries = _entries()
    selected = deterministic_select(entries, 12)
    assert _keys(selected) == sorted(_keys(entries))[:12]
    assert _keys(deterministic_select(reversed(entries), 12)) == _keys(selected)
    assert len(deterministic_select(entries)) == 16
    selected[0]["reports"][0]["status"] = "changed-detached-copy"
    assert all(entry["reports"][0]["status"] != "changed-detached-copy" for entry in entries)


def test_selection_never_reads_public_scores_or_hidden_outcomes():
    entries = _entries()
    before = _keys(deterministic_select(entries, 16))
    for index, entry in enumerate(entries):
        # These invalid reports must still be rejected by the original bundle
        # builder. Here they show that the selector cannot cherry-pick by H/V.
        entry["reports"] = ({"status": "pass" if index % 2 else "fail", "H": str(index)},)
    assert _keys(deterministic_select(entries, 16)) == before


def test_prompt_selection_matches_preregistered_raw_entries_and_ignores_presentation_order():
    entries, bundle = _multi_bundle()
    _, user, _ = messages(PARENT, bundle)
    feedback = json.loads(user)["feedback"]
    assert [pair["task"]["prompt"] for pair in feedback["paired_development"]] == [
        entry["task"].contract.prompt for entry in deterministic_select(entries)]
    assert feedback["public_role_summary"]["counts"]["tie"] == 16
    selected_twelve = json.loads(messages(PARENT, bundle, feedback_limit=12)[1])["feedback"]
    assert len(selected_twelve["paired_development"]) == 12
    reversed_bundle = deepcopy(bundle)
    reversed_bundle["source_bindings"].reverse()
    reversed_bundle["model_view"]["paired_development"].reverse()
    reversed_bundle["model_view_hash"] = digest(reversed_bundle["model_view"])
    for mode in ("contract_only", "evidence"):
        assert messages(PARENT, bundle, mode) == messages(PARENT, _reseal(reversed_bundle), mode)


@pytest.mark.parametrize("limit", [0, 17, 64, True, 1.5, "12"])
def test_selection_limits_fail_closed(limit):
    with pytest.raises(ValueError, match="preregistered integer"):
        deterministic_select(_entries(1), limit)
    with pytest.raises(ValueError, match="preregistered integer"):
        messages(PARENT, _bundle(), feedback_limit=limit)


def test_selection_rejects_hidden_entry_fields_and_non_development_tasks():
    entries = _entries(1)
    entries[0]["H"] = "PRIVATE_SENTINEL"
    with pytest.raises(ValueError, match="standard public-feedback"):
        deterministic_select(entries)
    entries = _entries(1)
    entries[0]["task"] = replace(entries[0]["task"], contract=replace(entries[0]["task"].contract, partition="final"))
    with pytest.raises(ValueError, match="development"):
        deterministic_select(entries)


def test_contract_only_contains_contracts_but_no_code_observation_or_score():
    bundle = _bundle(responses=({"actual": 99}, {"after_args": [[1, 2, 99]]}))
    _, user, _ = messages(PARENT, bundle, "contract_only")
    payload = json.loads(user)
    assert payload["public_context"] == PUBLIC_CONTEXT
    contract = payload["feedback"]["development_contracts"][0]
    assert contract["task"]["prompt"]
    assert contract["task"]["obligations"]
    assert contract["public_cases"][0]["expected"] == 3
    for forbidden in ("roles", "artifact", "checks", "observations", "status", "availability", "actual",
                      "after_args", "public_files", "same_delivered_content", "public_role_summary", "H", "V"):
        assert f'"{forbidden}":' not in user
    assert "# Fixture" not in user
    assert "solution.py" in payload["public_context"]["output_contract"]


def test_contract_only_is_invariant_to_executed_outcomes_and_missing_execution():
    passed = _bundle()
    failed = _bundle(responses=({"actual": 99}, {"after_args": [[1, 2, 99]]}))
    unknown = _bundle(read_only=True)
    assert messages(PARENT, passed, "contract_only") == messages(PARENT, failed, "contract_only")
    assert messages(PARENT, passed, "contract_only") == messages(PARENT, unknown, "contract_only")
    assert messages(PARENT, passed, "evidence") != messages(PARENT, failed, "evidence")


@pytest.mark.parametrize("mode", ["contract_only", "evidence"])
def test_host_hidden_receipt_metadata_cannot_change_model_context(mode):
    plain = _bundle()
    hidden = _bundle(responses=({"H": "HIDDEN_AUDIT_SENTINEL"}, {"H": "HIDDEN_AUDIT_SENTINEL"}))
    assert plain["record_hash"] != hidden["record_hash"]
    assert messages(PARENT, plain, mode) == messages(PARENT, hidden, mode)
    assert "HIDDEN_AUDIT_SENTINEL" not in messages(PARENT, hidden, mode)[1]


@pytest.mark.parametrize("mode", ["contract_only", "evidence"])
def test_both_modes_enforce_original_bundle_parent_and_projection_boundaries(mode):
    bundle = _bundle()
    with pytest.raises(ValueError, match="Changed parent"):
        messages(PARENT + "\nchanged", bundle, mode)
    injected = deepcopy(bundle)
    injected["H"] = "PRIVATE_SENTINEL"
    with pytest.raises(ValueError, match="Unexpected feedback bundle"):
        messages(PARENT, _reseal(injected), mode)
    injected = deepcopy(bundle)
    injected["model_view"]["paired_development"][0]["roles"]["current"]["H"] = "PRIVATE_SENTINEL"
    injected["model_view_hash"] = digest(injected["model_view"])
    with pytest.raises(ValueError, match="private model-view"):
        messages(PARENT, _reseal(injected), mode)


def test_evidence_retains_standard_public_projection_and_binding_hash():
    bundle = _bundle(responses=({"actual": 99}, {}))
    system, user, prompt_hash = messages(PARENT, bundle)
    feedback = json.loads(user)["feedback"]
    assert feedback["paired_development"] == bundle["model_view"]["paired_development"]
    assert feedback["public_role_summary"]["counts"]["win"] == 1
    assert prompt_hash == digest({"system": system, "user": user})
    for hidden in ("fixture-task", "fixture-family", "source_bindings", "execution_receipts", "rubric_hash", "pipeline_hash"):
        assert hidden not in user


@pytest.mark.parametrize("baseline,current,outcome", [
    ("fail", "pass", "win"), ("pass", "fail", "loss"),
    ("pass", "pass", "tie"), ("fail", "fail", "tie"),
    ("unknown", "pass", "unknown"), ("pass", "unknown", "unknown"),
    ("unknown", "fail", "unknown"), ("fail", "unknown", "unknown"),
    ("unknown", "unknown", "unknown"),
])
def test_public_role_summary_preserves_unknown_and_shared_failures(baseline, current, outcome):
    pair = {"roles": {"no_skill": {"status": baseline}, "current": {"status": current}}}
    summary = public_role_summary([pair])
    counts = summary["counts"]
    assert counts[outcome] == 1
    assert sum(counts[key] for key in ("win", "loss", "tie", "unknown")) == 1
    assert counts["both_fail"] == int(baseline == current == "fail")
    assert counts["both_pass"] == int(baseline == current == "pass")
    pair["H"] = {"no_skill": "pass", "current": "fail"}
    assert public_role_summary([pair]) == summary
    assert "not causal Skill effects" in summary["interpretation"]


def test_unexecuted_receipts_stay_unknown_in_evidence():
    _, user, _ = messages(PARENT, _bundle(read_only=True))
    feedback = json.loads(user)["feedback"]
    assert feedback["public_role_summary"]["counts"]["unknown"] == 1
    for role in feedback["paired_development"][0]["roles"].values():
        assert role["status"] == "unknown"
        assert all(observation["status"] == "unsupported" and "actual" not in observation
                   for check in role["checks"] for observation in check["observations"])


@pytest.mark.parametrize("mode", ["contract_only", "evidence"])
def test_conditional_policy_allows_rule_removal_and_keeps_syntax_only_parser(mode):
    system, user, _ = messages(PARENT, _bundle(), mode)
    for rule in ("Preserve / Repair / Restrict", "may delete", "not a globally mandatory policy",
                 "output protocol take precedence", "input preservation", "when to abstain",
                 "checks syntax only", "NO_UPDATE"):
        assert rule in system
    for section in ("## Mechanism", "## When", "## Procedure", "## Avoid"):
        assert section in system
    assert "JSON delivery contract describes future task solutions" in system
    assert json.loads(user)["public_context"] == PUBLIC_CONTEXT
    parsed = parse_update(CANDIDATE, PARENT)
    assert parsed["status"] == "candidate"
    assert parsed["deployment_authorized"] is False
    assert parse_update("NO_UPDATE", PARENT)["status"] == "no_update"


def test_mode_and_source_binding_mismatch_fail_closed():
    with pytest.raises(ValueError, match="Unknown conditional-feedback mode"):
        messages(PARENT, _bundle(), "hidden_audit")
    bundle = _bundle()
    bundle["source_bindings"] = []
    with pytest.raises(ValueError, match="One source binding"):
        messages(PARENT, _reseal(bundle))
