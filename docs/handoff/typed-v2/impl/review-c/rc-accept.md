# rc-accept: read-only review, lens "acceptance list and scope"

Reviewer id: rc-accept. Scope: batch "git diff de7346c" in the context of "git diff 8375ecb".
No tree file edited except this note. Scratch: /tmp/typed2-neutral/rc-accept/.

## Plan
- [x] Read IMPLEMENTATION-ORDER Steps 6, 7 and "Do not touch"
- [x] Read addendum D9, D10, D12, D13, D15, RP1-RP12
- [x] Read spec/read-plan.md section 4 (T1-T27) and spec/schedule-lock.md section 4
- [x] Run the full typed test suite once (707 passed in 81.93s, Python 3.13)
- [x] Map every "Accept when" item and T-case to a test (file::name) or mark missing
- [x] Check "Do not touch" against "git diff 8375ecb --stat" and "git status --short"
- [x] Check each addendum item is reflected in code
- [x] Check the smoke covers fresh, alias, fallback (probe), stop/resume after plan, kill/resume inside a fresh unit (spec 4.3)
- [x] Write findings (concrete failure scenarios only)

## Progress

- Suite: `tests/test_typed_*.py tests/test_typed2_*.py` -> `707 passed in 81.93s (0:01:21)`.
- Scope: `git diff 8375ecb --name-only` holds no file under skillopt/ outside T/; nothing outside T/, scripts/, tests/, docs/; no untracked or ignored .py under skillopt/; no edit of typed-v1 docs, DECISIONS*, DESIGN, IMPLEMENTATION-ORDER, spec/ or .sha256 in this batch (spec/read-plan.md and the addendum changed before de7346c, committed).

## Mapping (file::test; "core" = tests/test_typed_readplan_core.py, "rp" = tests/test_typed_readplan.py)

IMPLEMENTATION-ORDER Step 6, Accept when:
- default fields: order and every request as after step 5 -> test_typed2_shared.py::test_one_bench_per_type_sends_every_request_unit_cell_and_record_of_5w (5w golden; pins moved on purpose: s0..s5/frozen.json and solver-settings.json named, then removed before the unchanged digest), test_typed2_base.py::test_format_base_sends_every_request_and_cell_of_the_5x_tree
- learn_first same requests, other order -> test_typed_schedule.py::test_learn_first_same_units_requests_identities
- changed frozen file pauses -> test_typed_schedule.py::test_changed_frozen_file_pauses_before_any_call
- default lock call unchanged -> test_typed_schedule.py::test_default_lock_is_the_typed_v1_call
- reset inside the lock under unit_shared, bare under per_cell_plain -> test_typed_reads.py::test_the_alfworld_preparation_reset_is_locked_only_under_unit_shared; rp::test_the_pass_opens_real_panels_under_consent_with_registry_qualification_and_locked_resets

IMPLEMENTATION-ORDER Step 7, Accept when:
- guard refuses each altered case -> test_typed2_machinery.py::test_the_bound_guard_refuses_each_altered_case (7 cases), ::test_real_check_refuses_unbound_wrong_and_altered_snapshots
- no skillopt module outside typed loaded from the tree in the child -> test_typed2_machinery.py::test_bound_interpreter_runs_every_area_on_the_snapshot
- git status only T/, scripts/, tests/, docs/ -> checked here (git diff 8375ecb --name-only, git status --short)
- tree equals the 564-row list -> test_typed2_machinery.py::test_tree_equals_list

spec/schedule-lock.md section 4: T1 test_prepare_schedule_and_lock_fields; T2 test_interleaved_done_units_are_the_typed_v1_sequence; T3 test_learn_first_same_units_requests_identities; T4 test_learn_first_reads_mount_each_steps_frozen_state; T5 test_changed_frozen_file_pauses_before_any_call; T6 test_learn_first_resume_in_learning_and_in_reads; T7 test_resume_refuses_a_different_schedule; T8 test_consent_is_checked_in_every_read_unit_in_both_orders; T9 test_status_shows_schedule_and_phase; T10 test_default_lock_is_the_typed_v1_call; T11 test_unit_shared_two_cells_overlap_and_another_unit_waits; T12 test_unit_shared_setting_names_root_chain_unit; T13 test_the_lock_modes_and_the_schedules_under_the_bound_machinery (all in tests/test_typed_schedule.py).

spec/read-plan.md 4.2:
- T1 rp::test_prepare_seals_the_read_plan_and_refuses_forbidden_pairs, rp::test_a_resume_with_another_read_plan_is_a_hard_error, test_typed_cli.py::test_the_read_plan_options_parse_and_reach_their_adapters
- T2 test_typed_mount_identity.py::test_mount_identity_equals_the_fields_of_mount_for_every_arm_and_fixture, core::test_selection_hash_reduction_and_capture_objects, core::test_offered_ids_must_agree_between_the_identity_and_the_mount_record, rp::test_an_identity_exception_makes_its_pair_a_class_of_its_own (integration with every item kind: not built, rp-int says so)
- T3 rp::test_an_empty_library_at_every_step_reads_nine_units (both bases); CB27 part only through rp::test_the_pass_sends_nothing_and_writes_only_its_files
- T4 core::test_a_card_learned_at_step_k_splits_before_and_after, core::test_a_change_of_card_selection_or_offered_programs_splits_the_class; integration only through the configured smoke (sheet changed at step 4, historical)
- T5 core class rules + order assertions of rp::test_economy_smoke_reads_each_class_once_and_settles_every_other_pair; no change-at-step-5 integration fixture
- T6 core::test_a_type_id_only_difference_does_not_split_and_flips_are_counted, core::test_historical_base_card_less_and_unknown_items_have_the_identity_of_C, core::test_format_base_card_less_and_unknown_items_have_the_identity_of_C0
- T7 MISSING (finding F1)
- T8 core::test_item_identity_collision_attempts (b c h i j), core::test_two_items_that_swap_system_texts_give_other_lists (a), core::test_missing_or_unreadable_identity_is_its_own_fallback_class (k), core::test_first_request_mismatch_rule_on_summaries (m), core::test_every_hashed_component_splits_and_descriptive_fields_do_not (d e l); (f) moot (a blank card is refused by the mount), (g) not explicit
- T9 (ii) rp::test_an_edited_plan_pauses_and_is_restored_by_the_recovery; (iii) rp::test_an_edited_sealed_file_voids_the_plan_after_the_recovery; (iv) rp::test_a_deleted_alias_record_pauses_and_is_settled_again_with_equal_bytes; (v) rp::test_the_automatic_replay_runs_in_a_fresh_process_with_another_hash_seed, rp::test_a_replay_error_pauses_and_the_same_error_again_voids_the_plan; (i) (vi) at readout level test_typed_readout.py::test_alias_records_are_verified_and_a_tampered_plan_renders_no_read_table and core alias tests; (vii) rp::test_the_solver_settings_record_is_credential_free_write_once_and_written_under_full (pause only; "resume after restoring" untested)
- T10 core::test_replay_bytes_do_not_depend_on_the_hash_seed, rp::test_the_in_process_replay_is_equal_and_finds_every_planted_difference, rp::test_a_real_root_replay_without_the_qualification_is_different_and_starts_nothing, test_typed_cli.py::test_a_fake_smoke_stops_after_the_plan_and_resumes_with_the_owner_record (exit 3); changed panel and non-zero reembedded untested
- T11 rp::test_the_pass_sends_nothing_and_writes_only_its_files (no raising clients, no byte-equal ledger, parse_read_name of the plan units untested)
- T12 rp::test_the_pass_opens_real_panels_under_consent_with_registry_qualification_and_locked_resets (open_plan_panels level; qualification_paused through the pass and a kill after two registry entries untested)
- T13-T15 retired (RP1)
- T16 P5 rp::test_a_stop_inside_a_fresh_unit_resumes_without_sending_a_finished_cell_again (weak, finding F2); P2/P3/P3b test_typed_cli.py::test_a_kill_at_each_point_resumes_without_reading_a_class_twice_or_never; P4 T24; P12 the void tests; P1, P6, P7, P8, P11 not individually
- T17 rp::test_learn_first_with_full_reads_every_pair_fresh_and_writes_no_plan + unchanged interleaved tests
- T18 rp::test_fresh_units_are_the_full_units_and_their_first_requests_are_the_captures
- T19 rp::test_an_identity_exception_makes_its_pair_a_class_of_its_own, rp::test_a_capture_without_exactly_one_send_is_capture_failed, rp::test_an_unstable_second_embedder_run_reads_its_events_fresh, rp::test_a_post_read_mismatch_voids_every_alias_of_its_bench_and_reads_them_fresh, rp::test_a_pass_failing_twice_with_one_code_voids_the_plan_and_reads_all_35_pairs, core::test_embedder_instability_is_a_fallback
- T20 test_typed_readout.py (11 new tests, resolver to split phase)
- T21 rp::test_a_missing_receipt_after_the_plan_pauses_without_any_learning, test_typed_schedule.py::test_learning_is_closed_once_reading_has_begun
- T22 core::test_write_once_accepts_identical_and_refuses_different_bytes
- T23 rp::test_open_records_and_the_state_hold_hashes_and_counts_only, core::test_open_records_hold_hashes_and_counts_only
- T24 test_typed_cli.py::test_a_fake_smoke_stops_after_the_plan_and_resumes_with_the_owner_record
- T25 rp::test_the_solver_settings_record_is_credential_free_write_once_and_written_under_full
- T26 rp::test_the_automatic_replay_runs_in_a_fresh_process_with_another_hash_seed, rp::test_a_replay_error_pauses_and_the_same_error_again_voids_the_plan, heavy part in rp::test_the_in_process_replay_is_equal_and_finds_every_planted_difference
- T27 post-launch, not built (RP1)

Smoke 4.3: fresh, alias, probe fallback -> rp::test_economy_smoke_reads_each_class_once_and_settles_every_other_pair; stop and resume after the plan -> test_typed_cli.py::test_a_fake_smoke_stops_after_the_plan_and_resumes_with_the_owner_record; kill points of the pass -> test_typed_cli.py::test_a_kill_at_each_point_resumes_without_reading_a_class_twice_or_never; interrupt inside a fresh unit -> rp::test_a_stop_inside_a_fresh_unit_resumes_without_sending_a_finished_cell_again (in-process Stop; the SIGKILL inside a fresh unit is ops on dl, S3 b; plan carries read_order).

Addendum in code: D9 (prepare.read_plan_of / check_read_plan), D10 a-h (chain.plan, read_classes, settle, readplan core), D12 (S5 always a representative; void -> all fresh), D13 (heavy_for unit_shared; reads.preparation_reset), D15 (LEARN_WIDTHS in cells, WIDTHS in reads, both in sealed_constants), RP1 (no carry module), RP2 (write_solver_settings), RP3 (capture_first_request, alias counts), RP4/RP5/RP7 (readout), RP6 (replay_child, stop_after_plan), RP8/RP9 (mount_identity), RP10 (void_bench), RP11 (pass_failed), RP12 Q20-Q24 (check_read_plan, replay_error, solver_settings_changed, base card, pass_exception). Only T7 of R14 has no code or test.

## Findings
- F1 (must-fix): T7 label-neutrality guard missing from tests/typed2_bound_driver.py and the suite.
- F2 (minor): the P5 resume test cannot detect a re-sent finished cell (one-send rows are rewritten).

## Done
Read-only review; no tree file edited except this note.

## Tests
mkdir -p /tmp/typed2-neutral && cd <repo-root> && TMPDIR=/tmp/typed2-neutral <python> -m pytest -q -p no:cacheprovider tests/test_typed_*.py tests/test_typed2_*.py -> 707 passed in 81.93s (0:01:21)

## Choices
Integration-level gaps that the core tests cover (T2, T4-T6, T8) are listed, not reported: no concrete failure scenario found.

## Disagreements
None.

## Left for later steps
T7 before the smoke; the non-fake replay child (replay_services, plan_replay with a prepared manifest) is first exercised by the real smoke on dl.
