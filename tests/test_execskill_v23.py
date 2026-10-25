"""Route B v2.3 engineering fixtures: deterministic local hooks and synthetic cells only; no network/model calls."""
from __future__ import annotations

import copy
import json
from types import SimpleNamespace

import pytest

from skillopt.continual_eval.core import read_json
from skillopt.execskill import acceptance, protocol, reuse, solver, step
from skillopt.execskill.package import empty, with_
from skillopt.validator_pilot.api import digest
from tests.execskill_fakes_env import FakeSandbox, Script, procedure
from tests.test_execskill_acceptance import (N, VIEWS, fast_statistics, hooks, make_cells, packages, seal,  # noqa: F401
                                             workers)


def signature(package, view, table=None, bench="officeqa", **kwargs):
    with workers(table or {})(package, "item") as worker:
        return reuse.signature(bench, package, view, worker, **kwargs)


def test_zero_call_signature_is_the_shells_exact_first_request_and_faults_prevent_reuse():
    parent, candidate = packages("empty")
    view = next(iter(VIEWS.values()))
    silent = {N.id: {"applies": lambda view: True, "before_call": lambda view, state: None}}
    before, after = signature(parent, view), signature(candidate, view, silent)
    assert reuse.interchangeable(before, after, bench="officeqa")
    script = Script(["<answer>100</answer>"])
    actual = solver.solve("officeqa", view, "", candidate, script, worker=FakeSandbox(silent))
    assert actual["shell"]["calls"][0]["request_sha256"] == after["request_sha256"]
    faulty = {N.id: {"applies": lambda view: True, "before_call": lambda view, state: 42}}
    crashed = signature(candidate, view, faulty)
    assert crashed["request_sha256"] == before["request_sha256"] and crashed["faults"]
    assert not reuse.interchangeable(before, crashed, bench="officeqa")
    assert not reuse.interchangeable(before, {**after, "request_sha256": "different"}, bench="officeqa")
    assert not reuse.interchangeable(before, after, bench="alfworld")


def test_sheet_post_call_versions_and_placebo_content_are_part_of_identity():
    parent = empty(step="s0", evidence="engineering_fixture")
    feedback = procedure("p-spreadsheetbench-1-1", ("applies", "sheet_feedback"), origin="spreadsheetbench",
                         requests_second_call=True)
    candidate = with_(parent, step="s1", add=[feedback])
    view = {"instruction": "Sum the rows", "workbook_preview": "A1: 1", "required_answer_position": "A2"}
    before = signature(parent, view, bench="spreadsheetbench")
    after = signature(candidate, view, bench="spreadsheetbench")
    assert before["request_sha256"] == after["request_sha256"]
    assert after["post_call"][0]["version"] == feedback.sha256
    assert not reuse.interchangeable(before, after, bench="spreadsheetbench")
    sham = signature(candidate, view, bench="spreadsheetbench",
                     placebo={"procedures": {feedback.id: {"sheet_feedback": {"facts": ["inspect rows"]}}}, "seed": "x"})
    assert not reuse.interchangeable(after, sham, bench="spreadsheetbench")


def test_acceptance_c_sample_is_seeded_sealed_and_all_registered_runs_are_physical(tmp_path):
    found = seal(tmp_path / "one", kind="empty", reuse={"card_text": ""}, dup=True,
                 rule=protocol.PRACTICAL_RULE)
    plan = found["reuse"]
    assert found["version"].endswith("acceptance-sealed-v2-3")
    assert len(plan["card_sample"]["items"]) == 30 and plan["card_sample"]["seed"] == protocol.SEED
    assert plan["card_sample"]["runs"] == found["runs"]
    assert found["seals"]["reuse_sha256"] == digest(plan)
    assert read_json(tmp_path / "one" / "sealed.json") == found
    assert seal(tmp_path / "two", kind="empty", reuse={"card_text": ""}, dup=True,
                rule=protocol.PRACTICAL_RULE)["reuse"] == plan
    jobs = [job for block in acceptance.schedule(found).values() for job in block]
    assert {j["item"] for j in jobs if j["arm"] == "C"} == set(plan["card_sample"]["items"])
    assert sum(j["arm"] == "C" for j in jobs) == 30 * found["runs"]
    assert sum(j["arm"] == "S_dup" for j in jobs) == len(found["plan"]["astar"]) * found["runs"]
    # Reading the sealed plan again keeps exactly the resumed dispatch, independent of later hook implementations.
    assert acceptance.schedule(read_json(tmp_path / "one" / "sealed.json")) == acceptance.schedule(found)
    decision = acceptance.decide(make_cells(found), found)
    instrument = decision["guards"]["J6_dup"]["pairs"][0]
    assert instrument["sample_size"] == 30 and instrument["sample"] == "sealed_C_instrument"
    assert decision["contrasts"]["S'-C"]["whole_batch"] is None
    assert decision["contrasts"]["S-C"]["sample_size"] == 30
    assert decision["guards"]["J5"]["ok"]
    assert acceptance.reproduce(make_cells(found), found, decision)


def silent_round(tmp_path):
    table = hooks()
    table[N.id]["before_call"] = lambda view, state: None
    return seal(tmp_path, kind="empty", table=table, reuse={}, rule=protocol.PRACTICAL_RULE)


def test_reused_cells_are_zero_differences_with_logical_guards_and_physical_timing(tmp_path):
    found = silent_round(tmp_path)
    rows = found["reuse"]["reused"]["real"]
    assert all(arms["S'"] == arms["P_y"] == arms["P_i"] == "S" for arms in rows.values())
    cells = make_cells(found)
    decision = acceptance.decide(cells, found)
    assert decision["contrasts"]["S'-S"]["whole_batch"] == 0
    assert decision["contrasts"]["S'-P_y"]["whole_batch"] == 0
    assert decision["A"] == len(found["A"]) and decision["guards"]["J5"]["ok"]
    assert decision["request_reuse"]["physical_cells"] == len(cells)
    assert decision["request_reuse"]["cells"] and all(c["reused_from"]["arm"] == "S"
                                                      for c in decision["request_reuse"]["cells"])
    # An unknown's candidate L and parent H bounds must not invent a difference on a reused request.
    item = found["reuse"]["card_sample"]["items"][0]
    for cell in cells:
        if cell["task_id"] == item and cell["arm"] == "S":
            cell["judge"]["v2"]["token"] = "unknown"
    table = acceptance.table(acceptance.expanded_cells(cells, found))
    assert acceptance.differences(table, "S'", "S", [item]) == [0]
    assert acceptance.differences(table, "S'", "P_y", [item]) == [0]


def test_reuse_never_links_an_arm_to_itself_or_across_items_and_alfworld_is_excluded(tmp_path):
    old = seal(tmp_path)
    same = {"request_sha256": "same", "post_call": [], "faults": []}
    different = {**same, "request_sha256": "different"}
    signatures = {"real": {"a": {"S": same, "S'": different, "P_y": same, "S_dup": same},
                           "b": {"S": different, "S'": same}}}
    plan = reuse.from_signatures(old, signatures)
    assert plan["reused"] == {"real": {"a": {"P_y": "S"}}}
    alf = reuse.from_signatures({**old, "bench": "alfworld"}, signatures)
    assert alf["reused"] == {} and alf["card_sample"] is None
    broken = copy.deepcopy(silent_round(tmp_path / "silent"))
    item = broken["reuse"]["card_sample"]["items"][0]
    plan = copy.deepcopy(broken["reuse"])
    plan["reused"]["real"][item]["S'"] = "S'"
    broken = acceptance.with_reuse(broken, plan)
    with pytest.raises(ValueError, match="reuse itself"):
        acceptance.expanded_cells(make_cells(broken), broken)


def stub_step(tmp_path, monkeypatch, table=None):
    parent, candidate = packages("empty")
    setting = SimpleNamespace(extra={"configuration": protocol.MAIN_V2_3}, evidence="engineering_fixture",
                              cards={}, runtime={"officeqa": {}})
    st = step._Step(setting, SimpleNamespace(item_workers=workers(table or {})), "G", "officeqa", 1,
                    parent, tmp_path)

    def unit(name, work, **kwargs):
        attempt = tmp_path / name / "attempt-1"
        attempt.mkdir(parents=True, exist_ok=True)
        return work(attempt)

    monkeypatch.setattr(st, "unit", unit)
    monkeypatch.setattr(st, "solver", lambda *a, **k: pytest.fail("No endpoint should be created for zero jobs"))
    monkeypatch.setattr(step, "_feedback", lambda *a, **k: {})
    return st, candidate


def test_selftest_identical_requests_skip_both_arms_and_resume_the_plan(tmp_path, monkeypatch):
    st, candidate = stub_step(tmp_path, monkeypatch)
    generated = [{"id": "g1", "public": next(iter(VIEWS.values())), "private": {}, "benchmark": "officeqa"}]
    monkeypatch.setattr(step, "_sets", lambda *a: {"officeqa": generated})
    verdict = step._selftest(st, "selftest", candidate, {})
    assert verdict["cells"] == 0 and verdict["skipped_items"] == 1 and not verdict["blocked"]
    assert verdict["reason"] == "identical_requests_no_calls"
    assert verdict["sets"]["officeqa"]["accuracy"] == {"S'": None, "S": None}
    monkeypatch.setattr(step, "_pair_signatures", lambda *a, **k: pytest.fail("Resume uses the sealed identity"))
    assert step._selftest(st, "selftest", candidate, {}) == verdict


def test_selftest_skipped_items_remain_in_fault_and_format_denominators():
    cell = {"cell": {"arm": "S'", "task_id": "different"}, "judge": {"v2": {"token": "fail"}},
            "faults": [{"procedure": N.id}]}
    parent = {"cell": {"arm": "S", "task_id": "different"}, "judge": {"v2": {"token": "pass"}}}
    same = ["same-%d" % n for n in range(99)]
    verdict = step.selftest_verdict([cell, parent], {"officeqa": ["different"] + same}, {N.id},
                                    identical={"officeqa": same})
    assert verdict["fault_share"] == 0.01 and verdict["fault_items_denominator"] == 100
    assert not verdict["blocked"] and verdict["candidate_cells"] == 1


def test_training_prunes_first_then_skips_render_identical_items(tmp_path, monkeypatch):
    st, candidate = stub_step(tmp_path, monkeypatch)
    idle = procedure("p-officeqa-2-2", ("applies", "before_call"))
    candidate = with_(st.parent, step="s2", add=[N, idle])
    st.services.item_workers = workers({N.id: {"applies": lambda view: True},
                                        idle.id: {"applies": lambda view: False}})
    item = {"task_id": "one", "public": next(iter(VIEWS.values())), "private": {}}
    result = step._train_eval(st, {"run": [item]}, 1, st.parent, candidate, {})
    assert result["pruned"] == [idle.id]
    assert result["identical"] == ["officeqa/one"]
    assert result["differs"] == result["cells"] == 0
    assert result["verdict"]["fixed"] == result["verdict"]["broken"] == []
    assert not result["adopted"]


def test_old_round_without_reuse_keeps_its_decision_record(tmp_path):
    old = seal(tmp_path, rule=protocol.PRACTICAL_RULE)
    decision = acceptance.decide(make_cells(old), old)
    assert "reuse" not in old and "request_reuse" not in decision and "reuse" not in decision
    assert decision["version"] == "fivebench-execskill-v1-decision"
    assert acceptance.reproduce(make_cells(old), old, json.loads(json.dumps(decision)))


def test_zero_call_faults_still_count_if_the_later_execution_succeeds(tmp_path):
    faulty = hooks()
    faulty[N.id]["before_call"] = lambda view, state: 42
    sealed = seal(tmp_path, kind="empty", table=faulty, reuse={}, rule=protocol.PRACTICAL_RULE)
    decision = acceptance.decide(make_cells(sealed), sealed)  # fixture executions themselves have no fault
    assert decision["guards"]["J3"]["fault_items"] == len(sealed["plan"]["astar"])
    assert not decision["guards"]["J3"]["ok"]
    candidate = {"cell": {"arm": "S'", "task_id": "i"}, "judge": {"v2": {"token": "pass"}}}
    parent = {"cell": {"arm": "S", "task_id": "i"}, "judge": {"v2": {"token": "fail"}}}
    verdict = step.selftest_verdict([candidate, parent], {"officeqa": ["i"]}, {N.id},
                                    identical={"officeqa": []}, request_faults=["i"])
    assert verdict["blocked"] and verdict["fault_cells"] == 1
    trained = step.train_verdict({("S'", "i"): [candidate], ("S", "i"): [parent]}, ["i"], [], {N.id},
                                 predicate_faults=0, routed=1, sign=False, request_faults=["i"])
    assert not trained["adopted"] and trained["reason"] == "guard:own_faults"


def test_small_c_sample_and_withholding_twin_reuse_have_exact_registered_references(tmp_path, monkeypatch):
    sealed = seal(tmp_path, kind="empty", fires_n=lambda n: n < 4, reuse={}, rule=protocol.PRACTICAL_RULE)
    sample = sealed["reuse"]["card_sample"]
    assert set(sample["items"]) == set(sealed["plan"]["astar"]) and len(sample["items"]) == 4
    monkeypatch.setattr(reuse, "SEED", 1234567)
    assert reuse.card_sample(sealed) == sample  # re-read the sealed seed, not the process's current default
    same = {"request_sha256": "x", "post_call": [], "faults": []}
    other = {**same, "request_sha256": "y"}
    plan = reuse.from_signatures({**sealed, "card_is_parent": False}, {"real": {
        "i": {"S'": same, "S": other, "withhold:p": same, "restore:p": same, "C": other}}})
    assert plan["reused"] == {"real": {"i": {"withhold:p": "S'", "restore:p": "S'", "C": "S"}}}
    assert plan["card_sample"] is None

# The canonical v2.3 selection also covers E1-E5; the focused modules support narrower offline diagnostics.
from tests.test_execskill_v23_engineer import (  # noqa: E402,F401
    test_only_v23_train_proposals_request_32k_and_the_record_names_the_new_prompt,
    test_excerpts_keep_priority_anchors_merge_windows_and_count_omissions,
    test_payload_is_detached_and_alfworld_steps_are_never_shortened,
    test_v23_accepts_only_registered_pure_constants_and_legacy_stays_literal_only,
    test_v23_rejects_unregistered_module_expressions,
    test_procedure_and_worker_pin_the_policy_without_changing_old_frames,
    test_structure_normalization_and_c2_feedback_are_v23_only,
)
from tests.test_execskill_v23_delivery import (  # noqa: E402,F401
    test_v23_configuration_extends_every_table_without_changing_caps,
    test_e1_nominal_and_reservation_bounds_are_per_call,
    test_e1_smoke_projection_prices_new_prompt_and_output_reservation,
    test_e5_new_cases_have_unchanged_source_spans_and_separate_kinds,
    test_e5_multiple_blocks_refuse_by_default_last_is_explicit,
    test_e5_inline_fences_in_prose_never_start_or_close_blocks,
    test_v23_manifest_seals_prompt_policy_output_bound_and_extraction,
    test_e5_solver_delivery_reaches_native_only_for_the_new_configuration,
)

# Amendment 1's full-class acceptance and preserved training denominators are part of this canonical selection.
from tests.test_execskill_v23_acceptance_amendment import (  # noqa: E402,F401
    test_all_identical_items_have_no_cells_but_keep_all_statistics_and_denominators,
    test_full_classes_share_placebos_and_twins_with_c_not_only_with_parent,
    test_c_sample_prefers_already_dispatched_s_and_adds_s_only_for_supplements,
    test_instruments_remain_independent_when_every_request_is_identical,
    test_j4_excludes_interchangeable_parent_candidate_but_keeps_original_margin,
    test_j5_uses_only_actual_representative_cells_not_logical_copies,
    test_shared_unanswered_uses_dispatched_cells_and_never_excludes_identical_all,
    test_faulting_or_missing_identity_is_never_an_identical_all_item,
    test_skipped_probe_has_zero_gain_without_a_logical_cell,
    test_dispatch_counts_exist_on_small_and_early_undetermined_rounds,
)
from tests.test_execskill_v23_training_amendment import (  # noqa: E402,F401
    test_identical_items_keep_adoption_threshold_and_fault_cell_denominator,
    test_identical_items_keep_format_margin_at_registered_runs,
    test_generated_identical_items_count_once_and_all_identical_items_never_gain,
    test_skip_declaration_cannot_invent_items_or_drop_a_fault,
    test_legacy_verdict_omits_amendment_fields_and_keeps_its_exact_shape,
    test_training_dispatches_differences_but_evaluates_both_item_sources,
    test_training_all_identical_creates_no_endpoint_and_keeps_evaluated_items,
    test_legacy_training_still_dispatches_enabled_list_differences,
    test_selftest_has_the_same_unchanged_item_denominators,
    test_selftest_all_identical_is_unchanged_without_cells,
)

# Accepted Codex review findings are also covered by the canonical v2.3 entry point.
from tests.test_execskill_v23_scoring_review import (  # noqa: E402,F401
    test_shared_candidate_keeps_l_bound_against_different_controls,
    test_decision_contrasts_labels_and_tau_preserve_each_arms_registered_bound,
    test_validity_keeps_identical_all_real_and_generated_items_and_denominators,
)
from tests.test_execskill_v23_delivery_review import (  # noqa: E402,F401
    test_review_glued_prose_before_a_v1_python_block_preserves_program_and_span,
    test_every_successful_v1_case_retains_all_extraction_fields_under_recovery_variants,
)
from tests.test_execskill_v23_prompt_review import (  # noqa: E402,F401
    test_v23_single_prompt_requires_replay_tests_and_its_record_pins_that_prompt,
    test_v23_smoke_uses_the_single_mode_prompt_and_manifest_pins_both_modes,
)
from tests.test_execskill_v23_policy_review import (  # noqa: E402,F401
    test_review_example_rejects_x_and_retains_the_legacy_literal_verdict,
    test_all_builtin_constructors_are_audited_even_when_binding_is_later,
)

# Amendment 2: the repairable firing check is part of the canonical entry point.
from tests.test_execskill_v23_firing_amendment import (  # noqa: E402,F401
    test_idle_predicate_receives_only_keys_and_counts_then_fix_reaches_training,
    test_unchanged_idle_change_dies_after_registered_repairs_and_creates_no_train_cells,
    test_firing_change_preserves_existing_checks_and_uses_no_repairs,
    test_legacy_configurations_keep_idle_proposals_and_original_check_sequence,
    test_single_smoke_without_training_items_records_skip_and_keeps_replay_tests,
)
