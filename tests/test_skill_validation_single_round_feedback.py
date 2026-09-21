"""Scripted engineering fixtures: no model, real code execution, or efficacy claim."""
import json
from copy import deepcopy
from dataclasses import replace

import pytest

from skillopt.coevolution_v5.core import seal
from skillopt.skill_validation.checks import ExecutionCache, pipeline_hash, validate_callable
from skillopt.skill_validation.single_round_feedback import (
    build_feedback_bundle,
    candidate_from_response,
    messages,
    parse_update,
    skill_hash,
)
from skillopt.validator_pilot.api import digest
from tests.test_skill_validation_checks import ScriptedExecutor, artifact, rubric, task

PARENT = "## Mechanism\nPreserve declared constraints.\n## When\nOn local edits.\n## Procedure\nCheck required behavior.\n## Avoid\nInventing requirements."
CANDIDATE = "## Mechanism\nPreserve declared state.\n## When\nInput preservation is explicitly required.\n## Procedure\nCompare input state before and after execution.\n## Avoid\nPreserving state when the task requires in-place modification."


def _inputs(*, selected_rubric=None, inplace=False, responses=(), read_only=False):
    t = task(inplace=inplace)
    r = selected_rubric or rubric()
    cache = ExecutionCache(ScriptedExecutor(responses), read_only=read_only)
    artifacts = tuple(replace(artifact(t, condition=condition),
                              skill_hash=skill_hash("" if condition == "no_skill" else PARENT))
                      for condition in ("no_skill", "current"))
    reports = tuple(validate_callable(t, a, r, cache) for a in artifacts)
    return [{"task": t, "artifacts": artifacts, "reports": reports}], {
        "parent_skill": PARENT, "rubric": r, "pipeline_hash": pipeline_hash(r, cache),
        "execution_identity": cache.identity,
        "execution_records": tuple(cache.records.values()) + tuple(cache.missing_records.values()),
    }


def _bundle(**kwargs):
    entries, options = _inputs(**kwargs)
    return build_feedback_bundle(entries, **options)


def _reseal(value):
    value = deepcopy(value)
    value.pop("record_hash", None)
    return seal(value)


def test_actual_public_failure_is_projected_without_host_or_hidden_fields():
    bundle = _bundle(responses=({"actual": 99}, {"after_args": [[1, 2, 99]]}))
    system, user, prompt_hash = messages(PARENT, bundle)
    content = json.loads(user)
    pair = content["feedback"]["paired_development"][0]
    assert pair["roles"]["no_skill"]["obligations"] == {"obligation_0": "fail", "obligation_1": "pass"}
    assert pair["roles"]["current"]["obligations"] == {"obligation_0": "pass", "obligation_1": "fail"}
    observed = [o for c in pair["roles"]["current"]["checks"] for o in c["observations"]]
    assert any(o["after_args"] == [[1, 2, 99]] for o in observed)
    assert pair["roles"]["current"]["artifact"]["files"][0]["content"]
    assert pair["public_cases"][0]["expected"] == 3
    for hidden in ("fixture-task", "fixture-family", "fixture-project", "fixture-skill-version",
                   "source_hash", "rubric_hash", "pipeline_hash", "fixture:scripted-executor"):
        assert hidden not in user
    assert "SAME update policy" in system
    assert prompt_hash == digest({"system": system, "user": user})
    assert bundle["deployment_authorized"] is False


def test_parent_and_pipeline_are_bound_and_prompt_is_stable():
    entries, options = _inputs()
    first = build_feedback_bundle(entries, **options)
    second = build_feedback_bundle(deepcopy(entries), **deepcopy(options))
    assert first == second
    assert messages(PARENT, first) == messages(PARENT, second)
    with pytest.raises(ValueError, match="Changed parent"):
        messages(PARENT + "\nAnother rule", first)
    with pytest.raises(ValueError, match="pipeline mismatch"):
        build_feedback_bundle(entries, **{**options, "pipeline_hash": "0" * 64})


def test_role_presentation_order_does_not_change_feedback():
    entries, options = _inputs()
    first = build_feedback_bundle(entries, **options)
    entries[0]["artifacts"] = tuple(reversed(entries[0]["artifacts"]))
    entries[0]["reports"] = tuple(reversed(entries[0]["reports"]))
    second = build_feedback_bundle(entries, **options)
    assert first == second
    assert messages(PARENT, first) == messages(PARENT, second)


@pytest.mark.parametrize("private_key", ["audit", "hidden_tests", "scope_authorization", "near_miss"])
def test_private_entry_fields_are_rejected(private_key):
    entries, options = _inputs()
    entries[0][private_key] = "PRIVATE_SENTINEL"
    with pytest.raises(ValueError, match="unexpected/private"):
        build_feedback_bundle(entries, **options)


@pytest.mark.parametrize("field,value", [
    ("task_hash", "0" * 64), ("artifact_record_hash", "0" * 64),
    ("rubric_hash", "0" * 64), ("callable_task_hash", "0" * 64),
    ("audit", {"truth": "pass"}), ("status", "fail"),
])
def test_report_cannot_be_relabelled_or_have_private_fields(field, value):
    entries, options = _inputs()
    first, second = entries[0]["reports"]
    first = {**first, field: value}
    entries[0]["reports"] = (_reseal(first), second)
    with pytest.raises(ValueError, match="receipt replay"):
        build_feedback_bundle(entries, **options)


def test_non_development_parent_mismatch_and_pair_identity_fail_closed():
    entries, options = _inputs()
    original = deepcopy(entries)
    entries[0]["task"] = replace(entries[0]["task"], contract=replace(entries[0]["task"].contract, partition="final"))
    with pytest.raises(ValueError, match="development"):
        build_feedback_bundle(entries, **options)
    entries = deepcopy(original)
    base, current = entries[0]["artifacts"]
    entries[0]["artifacts"] = (base, replace(current, skill_hash=skill_hash("different")))
    with pytest.raises(ValueError, match="differs from parent"):
        build_feedback_bundle(entries, **options)
    entries[0]["artifacts"] = (base, replace(current, repeat=current.repeat + 1))
    with pytest.raises(ValueError, match="same repeat"):
        build_feedback_bundle(entries, **options)
    with pytest.raises(ValueError, match="Duplicate development"):
        build_feedback_bundle(original + original, **options)


def test_missing_or_wrong_execution_receipt_cannot_be_repaired():
    entries, options = _inputs()
    with pytest.raises(ValueError, match="receipt missing"):
        build_feedback_bundle(entries, **{**options, "execution_records": ()})
    records = list(deepcopy(options["execution_records"]))
    record = records[0]
    record["execution"]["source_hash"] = "0" * 64
    record["execution"] = _reseal(record["execution"])
    records[0] = _reseal(record)
    with pytest.raises(ValueError, match="another source"):
        build_feedback_bundle(entries, **{**options, "execution_records": tuple(records)})


def test_unknown_unexecuted_receipts_stay_unknown():
    bundle = _bundle(read_only=True)
    _, user, _ = messages(PARENT, bundle)
    for role in json.loads(user)["feedback"]["paired_development"][0]["roles"].values():
        assert role["status"] == "unknown"
        assert all(c["status"] == "unknown" for c in role["checks"])
        assert all(o["status"] == "unsupported" and "actual" not in o
                   for c in role["checks"] for o in c["observations"])


def test_irrelevant_rules_ids_order_and_versions_do_not_manufacture_feedback():
    fixed = rubric(("public_examples",))
    adapted = replace(rubric(("input_state", "public_examples")), version="different-version")
    adapted = replace(adapted, checks=tuple(replace(c, id="renamed-" + c.id) for c in adapted.checks))
    fixed_bundle = _bundle(selected_rubric=fixed, inplace=True)
    adapted_bundle = _bundle(selected_rubric=adapted, inplace=True)
    assert fixed_bundle["rubric_hash"] != adapted_bundle["rubric_hash"]
    assert messages(PARENT, fixed_bundle) == messages(PARENT, adapted_bundle)


def test_duplicate_equivalent_applicable_rules_do_not_add_information():
    one = rubric(("public_examples",))
    two = replace(one, checks=(one.checks[0], replace(one.checks[0], id="duplicate-check")))
    assert messages(PARENT, _bundle(selected_rubric=one)) == messages(PARENT, _bundle(selected_rubric=two))


def test_nested_private_field_cannot_be_injected_into_reused_prompt_bundle():
    bundle = _bundle()
    bundle["model_view"]["paired_development"][0]["task"]["audit"] = "PRIVATE_SENTINEL"
    bundle["model_view_hash"] = digest(bundle["model_view"])
    with pytest.raises(ValueError, match="private model-view"):
        messages(PARENT, _reseal(bundle))


@pytest.mark.parametrize("response", [
    None, "", "   ", {}, "{\"skill\": \"hi\"}", "```markdown\n" + CANDIDATE + "\n```",
    "preamble\n" + CANDIDATE, CANDIDATE.replace("## Avoid", "## Other"),
    "## Mechanism\n\n## When\nWhen\n## Procedure\nDo\n## Avoid\nBad",
    CANDIDATE + "\n## Extra\nMore", CANDIDATE + "\n\x00", "x" * 6001,
])
def test_invalid_model_responses_are_terminal_not_repaired(response):
    result = parse_update(response, PARENT)
    assert result["status"] == "invalid"
    assert result["candidate_skill"] is None
    assert result["deployment_authorized"] is False
    assert result["retry_authorized"] is False


@pytest.mark.parametrize("response", ["NO_UPDATE", PARENT, "\n" + PARENT + "\n"])
def test_no_update_is_normal_and_does_not_invent_a_candidate(response):
    assert parse_update(response, PARENT)["status"] == "no_update"


def test_candidate_is_only_a_bound_shadow_proposal():
    bundle = _bundle()
    result = candidate_from_response(CANDIDATE, PARENT, bundle)
    assert result["update"]["status"] == "candidate"
    assert result["update"]["candidate_skill_hash"] == skill_hash(CANDIDATE)
    assert result["feedback_hash"] == bundle["record_hash"]
    assert result["parent_skill_hash"] == skill_hash(PARENT)
    assert result["deployment_authorized"] is False
    assert result["update"]["deployment_authorized"] is False
