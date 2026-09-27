"""Complete-development boundary fixtures; no API or generated-code execution."""
import json
from copy import deepcopy
from dataclasses import replace

import pytest

from skillopt.skill_validation.checks import ExecutionCache, pipeline_hash, validate_callable
from skillopt.skill_validation.development_feedback import (
    MAX_DETAILS,
    MAX_PROMPT_BYTES,
    STRATA,
    build_development_feedback,
    messages,
)
from skillopt.skill_validation.models import SourceFile
from skillopt.skill_validation.single_round_feedback import MAX_CONTEXT_BYTES, build_feedback_bundle, skill_hash
from skillopt.validator_pilot.api import digest
from tests.test_skill_validation_checks import ScriptedExecutor, artifact, rubric, task
from tests.test_skill_validation_single_round_feedback import PARENT, _reseal


def _inputs(specs=None, *, count=4, repeats=2, padding=0, contract_padding=0, hidden=False):
    if specs is None:
        specs = [(index, repeat, "pass", "pass") for index in range(count) for repeat in range(repeats)]
    responses = []
    for _, _, baseline, current in specs:
        for status in (baseline, current):
            response = {"actual": 99} if status == "fail" else {"status": "unsupported"} if status == "unknown" else {}
            responses.append({**response, **({"H": "PRIVATE_AUDIT_SENTINEL"} if hidden else {})})
    cache = ExecutionCache(ScriptedExecutor(responses), max_executions=10000)
    r, entries = rubric(), []
    for index, repeat, _, _ in specs:
        original = task()
        t = replace(original, contract=replace(original.contract, task_id=f"development-fixture-{index}",
                                                prompt=original.contract.prompt + f" Public variant {index}."
                                                + "契" * contract_padding))
        artifacts = tuple(replace(artifact(t, condition=role, repeat=repeat),
                                  skill_hash=skill_hash("" if role == "no_skill" else PARENT),
                                  files=(SourceFile("solution.py", "# unexecuted fixture\n" + "#" * padding),))
                          for role in ("no_skill", "current"))
        reports = tuple(validate_callable(t, item, r, cache) for item in artifacts)
        entries.append({"task": t, "artifacts": artifacts, "reports": reports})
    return entries, {"parent_skill": PARENT, "rubric": r, "pipeline_hash": pipeline_hash(r, cache),
                     "execution_identity": cache.identity, "execution_records": tuple(cache.records.values())}


def _bundle(**kwargs):
    entries, options = _inputs(**kwargs)
    return build_development_feedback(entries, **options)


def _feedback(bundle, mode="evidence"):
    return json.loads(messages(PARENT, bundle, mode)[1])["feedback"]


def test_all_64_tasks_and_both_repeats_survive_old_context_limit():
    entries, options = _inputs(count=64, padding=900)
    with pytest.raises(ValueError, match="bounded UTF-8"):
        build_feedback_bundle(entries, **options)
    bundle = build_development_feedback(entries, **options)
    system, user, prompt_hash = messages(PARENT, bundle)
    feedback = json.loads(user)["feedback"]
    coverage = feedback["coverage"]
    assert coverage["independent_task_count"] == 64
    assert coverage["paired_repeat_count"] == 128
    assert coverage["repeat_denominators"] == [
        {"repeat": 0, "pair_count": 64, "task_count": 64},
        {"repeat": 1, "pair_count": 64, "task_count": 64},
    ]
    assert len(coverage["pair_summaries"]) == 128
    assert {row["repeat"] for row in coverage["detailed_pairs"]} == {0, 1}
    assert len(feedback["paired_development"]) == 16
    assert feedback["public_role_summary"]["counts"]["both_pass"] == 128
    assert len(user.encode("utf-8")) <= MAX_CONTEXT_BYTES
    assert len(system.encode("utf-8")) + len(user.encode("utf-8")) <= MAX_PROMPT_BYTES
    assert prompt_hash == digest({"system": system, "user": user})
    assert "not causal" in coverage["interpretation"]
    assert "not additional independent tasks" in coverage["interpretation"]


def test_failure_outside_first_sixteen_and_only_in_second_repeat_is_not_omitted():
    # Find a task outside the old first-16 hash selection, and make repeat 1
    # its sole regression. All 128 compact rows remain visible.
    base, _ = _inputs(count=64)
    hashes = sorted({entry["task"].contract.content_hash for entry in base})
    chosen_hash = hashes[-1]
    chosen_index = next(int(entry["task"].contract.task_id.rsplit("-", 1)[1]) for entry in base
                        if entry["task"].contract.content_hash == chosen_hash)
    specs = [(index, repeat, "pass", "fail" if index == chosen_index and repeat == 1 else "pass")
             for index in range(64) for repeat in range(2)]
    entries, options = _inputs(specs)
    bundle = build_development_feedback(entries, **options, detail_limit=1)
    feedback = _feedback(bundle)
    assert feedback["coverage"]["stratum_counts"]["loss"] == 1
    assert feedback["coverage"]["detailed_pairs"] == [{"task_slot": "task_063", "repeat": 1}]
    assert feedback["paired_development"][0]["roles"]["current"]["status"] == "fail"
    assert len(feedback["coverage"]["pair_summaries"]) == 128
    assert feedback["coverage"]["pair_summaries"][-1]["failed_checks"]["current"] == [
        {"method": "public_examples", "obligation_kind": "requested_behavior"}]


def test_fixed_status_strata_cover_all_categories_and_unknown_is_never_failure():
    specs = [(0, 0, "pass", "fail"), (1, 0, "fail", "fail"), (2, 1, "fail", "pass"),
             (3, 1, "unknown", "fail"), (4, 0, "pass", "pass"), (5, 1, "unknown", "unknown")]
    entries, options = _inputs(specs)
    bundle = build_development_feedback(entries, **options, detail_limit=5)
    coverage = _feedback(bundle)["coverage"]
    assert coverage["stratum_counts"] == {"loss": 1, "shared_fail": 1, "win": 1, "unknown": 2, "both_pass": 1}
    assert coverage["role_counts"]["no_skill"] == {"pass": 2, "fail": 2, "unknown": 2}
    selected = {(row["task_slot"], row["repeat"]) for row in coverage["detailed_pairs"]}
    detailed_rows = [row for row in coverage["pair_summaries"] if (row["task_slot"], row["repeat"]) in selected]
    assert {row["stratum"] for row in detailed_rows} == set(STRATA)
    unknown = next(row for row in detailed_rows if row["stratum"] == "unknown")
    assert unknown["statuses"] == {"no_skill": "unknown", "current": "fail"}
    assert unknown["failed_checks"]["no_skill"] == []
    assert unknown["failed_checks"]["current"]


def test_determinism_caller_order_role_order_receipt_order_and_json_roundtrip():
    entries, options = _inputs(count=10)
    first = build_development_feedback(entries, **options, detail_limit=3)
    reversed_entries = [{**entry, "artifacts": tuple(reversed(entry["artifacts"])),
                         "reports": tuple(reversed(entry["reports"]))} for entry in reversed(entries)]
    second = build_development_feedback(reversed_entries,
                                       **{**options, "execution_records": tuple(reversed(options["execution_records"]))},
                                       detail_limit=3)
    assert first == second
    assert messages(PARENT, first) == messages(PARENT, json.loads(json.dumps(second)))
    assert first["coverage"]["detailed_pair_count"] == 3


def test_context_budget_reduces_full_details_without_truncating_sources_or_coverage():
    entries, options = _inputs(count=64, padding=8000)
    bundle = build_development_feedback(entries, **options)
    system, user, _ = messages(PARENT, bundle)
    feedback = json.loads(user)["feedback"]
    assert 1 <= len(feedback["paired_development"]) < MAX_DETAILS
    assert len(feedback["coverage"]["pair_summaries"]) == 128
    assert len(user.encode("utf-8")) <= MAX_CONTEXT_BYTES
    assert MAX_PROMPT_BYTES == 120000
    assert len(system.encode("utf-8")) + len(user.encode("utf-8")) <= MAX_PROMPT_BYTES
    assert feedback["coverage"]["detailed_pair_count"] == len(feedback["paired_development"])
    for pair in feedback["paired_development"]:
        assert len(pair["roles"]["current"]["artifact"]["files"][0]["content"]) > 8000


def test_contract_control_and_evidence_enforce_combined_120k_utf8_budget():
    entries, options = _inputs(count=20, contract_padding=3000)
    passed = build_development_feedback(entries, **options)
    specs = [(index, repeat, "pass", "unknown") for index in range(20) for repeat in range(2)]
    changed, changed_options = _inputs(specs, padding=4000, contract_padding=3000)
    unknown = build_development_feedback(changed, **changed_options)
    assert messages(PARENT, passed, "contract_only") == messages(PARENT, unknown, "contract_only")
    for bundle in (passed, unknown):
        for mode in ("evidence", "contract_only"):
            system, user, _ = messages(PARENT, bundle, mode)
            assert len(system.encode("utf-8")) + len(user.encode("utf-8")) <= 120000
            assert len(user.encode("utf-8")) > len(user)
        feedback = _feedback(bundle, "contract_only")
        assert 1 <= len(feedback["development_contracts"]) < MAX_DETAILS
        assert bundle["coverage"]["paired_repeat_count"] == 40


@pytest.mark.parametrize("limit", [0, 17, 128, True, "16", 1.5])
def test_detail_limit_is_bounded_and_typed(limit):
    entries, options = _inputs(count=1)
    with pytest.raises(ValueError, match="Detail limit"):
        build_development_feedback(entries, **options, detail_limit=limit)


@pytest.mark.parametrize("private_key", ["H", "audit", "hidden_tests", "private_metadata"])
def test_private_entry_fields_are_rejected_even_if_that_pair_would_not_be_selected(private_key):
    entries, options = _inputs(count=10)
    entries[-1][private_key] = "PRIVATE_SENTINEL"
    with pytest.raises(ValueError, match="unexpected/private"):
        build_development_feedback(entries, **options, detail_limit=1)


def test_unselected_reports_and_receipts_are_still_replayed_and_mismatch_rejected():
    entries, options = _inputs(count=10)
    damaged = deepcopy(entries)
    damaged[-1]["reports"] = (_reseal({**damaged[-1]["reports"][0], "status": "fail"}), damaged[-1]["reports"][1])
    with pytest.raises(ValueError, match="receipt replay"):
        build_development_feedback(damaged, **options, detail_limit=1)
    records = deepcopy(options["execution_records"])
    records[-1]["execution"]["source_hash"] = "0" * 64
    records[-1]["execution"] = _reseal(records[-1]["execution"])
    records = (*records[:-1], _reseal(records[-1]))
    with pytest.raises(ValueError, match="another source"):
        build_development_feedback(entries, **{**options, "execution_records": records}, detail_limit=1)
    with pytest.raises(ValueError, match="receipt missing"):
        build_development_feedback(entries, **{**options, "execution_records": options["execution_records"][:-1]}, detail_limit=1)


@pytest.mark.parametrize("target", ["summary_count", "pair_status", "binding_repeat", "binding_hash", "nested_detail",
                                   "private_coverage", "control"])
@pytest.mark.parametrize("mode", ["evidence", "contract_only"])
def test_resealed_derived_summary_binding_detail_and_control_tampering_is_rejected(target, mode):
    bundle = _bundle(count=2)
    if target == "summary_count":
        bundle["coverage"]["stratum_counts"]["loss"] = 99
    elif target == "pair_status":
        bundle["coverage"]["pair_summaries"][0]["statuses"]["current"] = "fail"
    elif target == "binding_repeat":
        bundle["selected_source_bindings"][0]["repeat"] += 10
    elif target == "binding_hash":
        bundle["selected_bundle"]["source_bindings"][0]["task_hash"] = "0" * 64
        bundle["selected_bundle"] = _reseal(bundle["selected_bundle"])
        bundle["selected_source_bindings"] = deepcopy(bundle["selected_bundle"]["source_bindings"])
    elif target == "nested_detail":
        bundle["selected_bundle"]["model_view"]["paired_development"][0]["roles"]["current"]["H"] = "PRIVATE"
        bundle["selected_bundle"]["model_view_hash"] = digest(bundle["selected_bundle"]["model_view"])
        bundle["selected_bundle"] = _reseal(bundle["selected_bundle"])
    elif target == "private_coverage":
        bundle["coverage"]["H"] = "PRIVATE"
    else:
        bundle["contract_only"]["development_contracts"][0]["task"]["source"] = "PRIVATE"
    with pytest.raises(ValueError, match="source-bound receipt replay"):
        messages(PARENT, _reseal(bundle), mode)


def test_serialized_host_entry_extra_fields_and_report_relabeling_are_rejected_on_load():
    bundle = _bundle(count=1)
    bundle["entries"][0]["H"] = "PRIVATE"
    with pytest.raises(ValueError, match="unexpected/private"):
        messages(PARENT, _reseal(bundle))
    bundle = _bundle(count=1)
    report = bundle["entries"][0]["reports"][0]
    report["status"] = "fail"
    bundle["entries"][0]["reports"][0] = _reseal(report)
    with pytest.raises(ValueError, match="receipt replay"):
        messages(PARENT, _reseal(bundle))


def test_contract_control_is_invariant_to_all_outcomes_sources_and_stratified_selection():
    pass_entries, pass_options = _inputs(count=20)
    fail_specs = [(index, repeat, "pass", "fail" if index == 19 and repeat == 1 else "unknown")
                  for index in range(20) for repeat in range(2)]
    fail_entries, fail_options = _inputs(fail_specs, padding=400)
    passed = build_development_feedback(pass_entries, **pass_options, detail_limit=1)
    failed = build_development_feedback(fail_entries, **fail_options, detail_limit=1)
    assert messages(PARENT, passed, "contract_only") == messages(PARENT, failed, "contract_only")
    assert passed["coverage"]["detailed_pairs"] != failed["coverage"]["detailed_pairs"]
    assert len(_feedback(passed, "contract_only")["development_contracts"]) == 16
    user = messages(PARENT, failed, "contract_only")[1]
    for forbidden in ("roles", "artifact", "checks", "observations", "status", "availability", "actual",
                      "public_files", "same_delivered_content", "public_role_summary", "coverage", "H", "V",
                      "execution_records", "selected_source_bindings", "source_hash"):
        assert f'"{forbidden}":' not in user
    assert "# unexecuted fixture" not in user


@pytest.mark.parametrize("mode", ["evidence", "contract_only"])
def test_hidden_receipt_metadata_changes_no_model_text(mode):
    plain, hidden = _bundle(count=2), _bundle(count=2, hidden=True)
    assert plain["record_hash"] != hidden["record_hash"]
    assert messages(PARENT, plain, mode) == messages(PARENT, hidden, mode)
    user = messages(PARENT, hidden, mode)[1]
    for private in ("PRIVATE_AUDIT_SENTINEL", "development-fixture-", "fixture-family", "fixture-project",
                    "execution_records", "selected_source_bindings", "pipeline_hash", "rubric_hash"):
        assert private not in user


def test_empty_duplicate_too_many_nondevelopment_and_parent_mismatch_fail_closed():
    entries, options = _inputs(count=1)
    with pytest.raises(ValueError, match="At least one"):
        build_development_feedback([], **options)
    with pytest.raises(ValueError, match="Duplicate development"):
        build_development_feedback(entries + entries, **options)
    oversized, oversized_options = _inputs(count=65)
    with pytest.raises(ValueError, match="Too many development"):
        build_development_feedback(oversized, **oversized_options)
    wrong = deepcopy(entries)
    wrong[0]["task"] = replace(wrong[0]["task"], contract=replace(wrong[0]["task"].contract, partition="final"))
    with pytest.raises(ValueError, match="development"):
        build_development_feedback(wrong, **options)
    bundle = build_development_feedback(entries, **options)
    with pytest.raises(ValueError, match="Changed parent"):
        messages(PARENT + "\nchanged", bundle)
    with pytest.raises(ValueError, match="Unknown development-feedback mode"):
        messages(PARENT, bundle, "H")
