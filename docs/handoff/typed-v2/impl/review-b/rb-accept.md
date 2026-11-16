# Review rb-accept: acceptance list and scope (Steps 1 to 5, 5b, 5w, 5x)

Reviewer rb-accept, read-only, 2026-11-12. Code under review: `git diff 8375ecb` (batch 1 at cdf85b6 plus the
uncommitted batch 2: 5b, 5w, 5x). Implementer reports were read as claims; every item below was checked in the code
or by running the tests. `T/` = `skillopt/execskill/typed/`.

Test run (once, Python 3.13.12, from the tree root):
`TMPDIR=/tmp/typed2-neutral python -m pytest -q -p no:cacheprovider tests/test_typed_*.py tests/test_typed2_*.py`
-> `529 passed in 22.80s`, no skip, no warning. Extra static check: every `T/*.py`, `scripts/run_typed.py` and
`tests/test_typed*.py` compiles under Python 3.10.20 (so the 3.11 grammar holds); no 3.12+ API found by grep.

## 1. "Accept when" items and the tests that prove them

Step 1
- No `typed-v1` literal in `T/` except the two draw tags and comments: NO TEST. Holds by grep: only `SLICE_TAG`,
  `EXAMPLE_TAG` and docstrings / comments.
- typed-v1 root, manifest, state, library and type map refused:
  `tests/test_typed2_identity.py::test_own_root_refuses_every_other_typed_version`,
  `::test_every_command_refuses_a_typed_v1_root_before_touching_it`, `::test_read_panel_refuses_a_typed_v1_root_before_any_read`
  (root); `::test_load_manifest_refuses_a_typed_v1_manifest_and_root` (manifest); `::test_a_typed_v1_chain_state_is_refused`
  (state); `::test_a_library_or_type_map_of_another_version_is_refused` (library, type map).
- Different container tags: `tests/test_typed2_services.py::test_typed_v1_and_typed_v2_get_different_container_tags_for_the_same_chain_and_unit`.
- One helper per test file: NO TEST (structural). Holds: the only constructors are `smoke.fake_services` and
  `tests/test_typed_reads.py::services_for` (plus the real-wiring helper `real_services` in `test_typed2_services.py`).

Step 2
- 3,000 / 4,500 pass, 4,501 fails: `tests/test_typed_cards.py::test_content_count_and_the_4500_hard_limit`;
  `tests/test_typed_writers.py::test_write_card_accepts_up_to_4500_content_characters_and_12_bullets`,
  `::test_write_card_rejects_above_4500_characters_or_12_bullets_and_names_the_measured_cause`.
- Trailing newline: `tests/test_typed_cards.py::test_a_final_newline_changes_nothing_and_the_typed_v1_loss_is_gone`.
- Golden first attempt and content retry: `tests/test_typed_writers.py::test_card_requests_equal_the_golden_typed_v1_bytes`,
  `::test_card_requests_equal_the_committed_typed_v1_writer_except_the_documented_length_retry` (base 'format';
  under 'historical' D17 adds the base block by design).
- `chars` in attempt row, decision, skill: `tests/test_typed_chain.py::test_card_chars_are_content_characters_in_the_attempt_the_decision_and_the_skill`.

Step 3
- Both F6 losses read: `tests/test_typed_replies.py::test_the_two_typed_v1_losses_are_read`.
- Parity with the frozen reader: `::test_parity_with_frozen_reader`.
- Never raises, never executes: `::test_reader_never_raises`, `::test_reader_does_not_execute`,
  `::test_resources_is_a_problem_not_an_exception`, `::test_fixture_table`.
- Two programs for one change are a problem: `::test_two_different_programs_are_a_problem_never_a_guess`.

Step 4
- 22 rows, legal and illegal example each through the real screen: `tests/test_typed_engineer_prompt.py::test_rule_table_shape`,
  `::test_rule_examples_match_screen`.
- Dropped row never reaches a gate unit, promoted third row does:
  `tests/test_typed_chain.py::test_real_writer_rows_promote_a_third_proposal_and_nothing_else_reaches_a_unit`,
  `::test_slot_rows_run_units_other_rows_get_zero_call_decisions`.
- At most 5 writer calls: `tests/test_typed_writers.py::test_at_most_five_writer_calls_per_unit_attempt`,
  `::test_every_promotion_scenario_follows_the_rule_and_the_call_bound`;
  `tests/test_typed_chain.py::test_at_most_five_writer_calls_per_programs_unit_attempt`.
- Interruption keeps every send: `tests/test_typed_writers.py::test_an_interruption_inside_the_loop_keeps_every_send_in_the_calls_file`;
  `tests/test_typed_chain.py::test_an_interruption_inside_the_promotion_loop_keeps_every_send_in_the_calls_file`.
- Smoke or gate failures promote nothing: `tests/test_typed_chain.py::test_a_smoke_fault_or_a_gate_rejection_of_a_slot_candidate_promotes_nothing`.
- Frozen `policy.check` call unchanged: `tests/test_typed_writers.py::test_the_frozen_screen_call_is_unchanged`.

Step 5
- Integer forms = D5 formulas (property): `tests/test_typed_gate_stats.py::test_property_integer_forms_equal_d5_fractions`,
  `::test_exhaustive_small_slices_hit_the_exact_boundaries`; `tests/test_typed2_gate.py::test_integer_forms_through_gates_equal_the_D5_formulas`.
- Every decision reproduced by `gates.recompute`: `tests/test_typed2_gate.py::test_every_stored_decision_is_reproduced_by_recompute_and_runs_stay_within_R`;
  member verdicts `tests/test_typed2_shared.py::test_shared_verdict_accepts_only_the_home_rule_and_every_member_and_recompute_rebuilds_it`.
- At most R requests per item and arm, re-runs counted: same test as above,
  `tests/test_typed2_gate.py::test_an_infrastructure_unknown_gate_cell_pauses_is_rerun_once_archived_and_counted`,
  `::test_a_recovered_call_reruns_its_own_unit_cell_once_and_never_a_cell_of_another_unit`.
- Model-side unknown never re-run: `tests/test_typed2_gate.py::test_a_model_side_unknown_run_scores_zero_and_is_never_run_again`,
  `::test_a_model_side_unknown_cell_is_never_marked_for_rerun`.
- Shared arms run no cell; `plan.json` identical after resume: `tests/test_typed2_gate.py::test_shared_arms_run_no_cell_and_plan_json_is_identical_after_a_resume`,
  `::test_a_round_two_text_equal_to_round_one_is_the_earlier_arm`; `tests/test_typed2_shared.py::test_resume_inside_a_member_unit_runs_no_finished_cell_again`.
- `no_harm` returns the stored record: `tests/test_typed2_gate.py::test_no_harm_returns_the_stored_record_on_resume`.
- Read units once per item: `tests/test_typed2_gate.py::test_read_units_still_run_once_per_item_with_bare_labels`.
- Gap (DESIGN 5 test list, not an accept item): sharing case (d) has no dedicated test (still listed by 5w).

## 2. Scope ("Do not touch")

- `git diff 8375ecb --name-only`: only `T/`, `scripts/run_typed.py`, `tests/`, `docs/`. No untracked `.py` under
  `skillopt/`; no new module under `X/`. The tree passes `shasum -c` against both machinery lists (564 + 64 rows); the
  list files have the pinned sha256 (`3c37fd...599f`, `75ad90...7a48`).
- Draw keys unchanged: `SEED = 20261110`, `SLICE_TAG = 'typed-v1:%s:slices'`, `EXAMPLE_TAG = 'typed-v1:writer-examples'`.
- ORDER, SLICES, CAPS, WIDTHS, READ_ARMS, CARD_ROUNDS, CARD_ATTEMPTS unchanged; library / type map only their literals.
- Protected docs: `docs/handoff/typed-v1/`, `DECISIONS.md`, `DESIGN.md`, `IMPLEMENTATION-ORDER.md`, the `.sha256`
  lists unchanged. `spec/read-plan.md` changed in commit cdf85b6: the coordinator's corrected spec (addendum 18:38,
  "1,326 lines; fix1, two checkers, fix2"; the file has 1,326 lines). The addendum changes are append-only (0 removed
  lines; the working tree adds the coordinator's RP13 section).
- One renamed test (`test_alfworld_programs_use_the_v295_prompt_family` -> `..._typed_engineer_prompt`): the
  DESIGN-mandated deletion of `ALFWORLD_PROMPTS`, with a stronger body. No other test removed.

## 3. Addendum decisions in code

D2 `T/cards.py`, `W.write_card`; D3 `T/engineer_prompt.py`, `W.propose_programs`, `_bounded_entry`, hooks check;
D4 `T/replies.py`; D5 `T/gatestats.py`, `C.gate_arm` / `compare`; D13 (fields only) `MEMORY_LOCKS`,
`MEMORY_LOCK_DEFAULT`, `Services.lock_setting`, `heavy(bench, unit=None)`; D15 `LEARN_WIDTHS` in `C.cells`,
`WIDTHS` in `reads`, both sealed and compared by `load_manifest`; O1 `gatestats.arm_runs` + unchanged re-run
predicate; O2 `machinery.DATA_LIST_SHA256`; O3 caps sealed, ledger cap from the manifest; O4 `draw_keys`; O5
`baseline_selected`; O6 `fired` = count of R cells, `fired_cells`; O7 `no_hook_function`; O8 15 pinned sentences;
O9 ops only; O10 no read-plan code in this tree; O11 binary scores, `arm_runs` refuses others; O12 list forms;
fired-subset informational fields `se_points_fired`, `se_points_scaled`. All present.

D17 (5b): `base_card` field sealed inside `record_sha256` (`prepare.prepare`), refused when missing or unknown by
`load_manifest`, `chain.run` (before anything is written) and `_open_state` (resume with another base); B arm =
`system_card(b, '')`; noise `B#1..3`, no-harm baseline `B@noise`, new type's F shared from `B@noise`; unknown and
card-less items mount the base (RP12 / Q23); C0 and C unchanged; writers' base block only where it adds; lengths count
the learned text only. Tests: `tests/test_typed2_base.py` (16). Note: the 'format' golden is re-pinned to the 5x tree
(self-referential since 5w); the 'format' equivalence is still held by structural checks (B mounts the format block,
no `base_card` key in non-solver requests, B = C0 record but the arm).

D16 (5x): members after typing; member learn units; member gate units with the D16 names; checks only after the
home rule; `member_harm` + bench; O5 member baseline after a card (`member-<b'>-outcomes-card` shared from the card's
member arm); `shared_verdict` / `recompute`; readout "Related gain"; one-bench types byte-identical to 5w (golden
`tests/test_typed2_shared.py::test_one_bench_per_type_sends_every_request_unit_cell_and_record_of_5w`). Present.

## 4. Implementer "Disagreements" and "Left for later" items

Resolved: 3 (A2' block ownership, implemented, parity tests); 4b item 4 (calls file across attempts:
`_keep_earlier_sends`); 4c item 1 (candidate key: `candidate_arm`; zero-call rows skip recompute); 5m (identity_fn,
plan.json, shared_arm_mismatch); 5s (re-exports, fired counts, gate_verdict, readout); 5b -> 5w / 5x (B labels,
identity_fn base, member blocks).

Still listed for later: Step 7 items of 1m, 2a, 3, 4a (REQUIRED scan, check 6, bound driver); 5w case (d) test, ops
helpers, Step 6 `heavy(bench, unit)`; 5x ops helpers.

Dropped (neither resolved nor listed again):
- 5b: "Readout / reports: show the manifest's base_card and state that typed-v2 starts from C, next to the C row"
  (finding F2).
- 1b: "the prepare command should print machinery_code" (spec/identity.md 1.10 and its launcher row; finding F3).
- 1b / 4c: "a real run requires limits == DEFAULT_LIMITS": only the `tau_rule` half is enforced (`real_services`);
  no current code path gives run-mode services other limits, so no failure today.
- 1a: DESIGN 5's "cap projection that includes the ALFWorld step" test was never assigned (O3 closed by the ops
  projection F12).
- 4c item 3: card-writer and describer units still rewrite their calls file per attempt (ledger keeps the charges).
- 4a Disagreements 1 and 2 (the [import] sentence; rewrites of some attribute names): open proposals for the Codex
  review, no recorded answer.

## 5. Findings

- F1 (minor, affects data): D17's operational value is not in the operations hand-off. Code default 'format';
  IMPLEMENTATION-ORDER Step 7 "Handed to operations" and DESIGN 6 name `prepare` with `--memory-lock unit_shared`
  only. The smoke root and the run root are prepared separately and nothing compares their `base_card`. A run root
  prepared from that list seals 'format' and learns from C0, against D17 and against a smoke prepared with
  'historical'. The only signal is the printed `base_card`. Fix: add `--base-card historical` for both roots to the
  coordinator's ops list (addendum) and make the ops launcher stop unless the printed `base_card` is 'historical' for
  both roots.
- F2 (minor): the readout neither shows the sealed `base_card` nor says that the learned arms compose on C
  (D17 "Reporting"); dropped 5b item. A 'historical' run's readout prints S1..S5 and `gain_over_C0` with no base
  label, so C's +11 to +20 points can be read as learned gain. Fix: print `base_card` (manifest / state) in the
  readout header and beside the C row.
- F3 (minor): `scripts/run_typed.py prepare` prints no `machinery_code` (spec/identity.md 1.10: "the prepare command
  prints the record so the launcher can stop at once"); the spec's launcher row "stop unless the printed
  `machinery_code.bound` is true" cannot work. An unbound prepare is found only when `run` refuses at `start_checks`
  (no paid call; the root is lost). Fix: add `machinery_code` to the printed prepare summary.

No blocker or must-fix found in the lens.
