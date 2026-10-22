# M2b progress (five-bench step wiring: SQ tail acceptance, LM J7, ALF fresh supply)

Started 2026-10-22 18:05 CST. Target 20:05, hard stop 20:35.

## Status (all done 18:4x; only the final report remains)
- [x] read spec (coordination, registrar 17:0x/17:3x, protocol, registration 3.1/3.3/6.4, I1-1)
- [x] (1) SearchQA acceptance from the kept tail
- [x] (2) LiveMath J7 options-only probe + decision; pool counts
- [x] (3) ALFWorld fresh-supply pool function + room-group slices
- [x] mutation entries 102-107
- [x] targeted tests

## Notes
- 18:1x spec read. M1 confirmed field names (coordination log 18:1x): `data.searchqa_tail` {path, sha256};
  `setting.extra["searchqa_tail"] = {**data.searchqa_tail, "exclusion": data.exclusion["searchqa_test_exclusion"]}`;
  `supply.alfworld_pool(supply_record, views_record, runtime=)` -> (items, counts); `supply.views_record(supply_record,
  views, cut, runtime=)` called by make-items (M1 edits run_execskill.py).
- J7 decision already exists: `acceptance._probe` (gain >= 0.10 AND one-sided p < 0.05, registration §6.4; tested by
  test_execskill_acceptance::test_t_acc_2_j7_options_only_probe_rejects_a_shortcut). Missing: probe cells got the full
  stem (step `_accept` tasks). Fix in step (`_round_tasks` / `_options_only`) with examiner's transform factored out
  (`examiner.shortcut_public`, behaviour-preserving).
- P_i already off on ALFWorld/SearchQA (`placebo.PI_BENCHES`).
- Pool counts (training pool via v3 manifest data pins, `supply.export_pool`, no test file): LiveMath 283 = 129
  meta-present + 154 meta-absent; registered cut run 119 (65 meta) + accept 100 (0 meta) + probe 64 (64 meta) = 283,
  0 left over (fits exactly, no slack). SearchQA pool 600: smoke 280 + run 300 (20 spare). SearchQA tail (smoke-inputs
  task 4 dry run): 11,378 items -> 1,000 accept after exclusion. Tail file ~50 MB (est. 4.25 KB/item) < read_json's
  64 MB cap.
- Plan: step.py `_cut` (SQ pool run + kept-tail accept; ALF run/accept room groups only + views/runtime check; others
  as before), `_tail`, `_items_of` reads the tail for SQ accept ids, `_blocks` ALF whole rooms in seeded room order,
  `_round_tasks`/`_options_only` (J7). supply.py `views_record`, `alfworld_pool`. New tests in
  tests/test_execskill_fivebench_step.py. Mutations 102-107.

## Results (18:4x)
- Code: step.py `TAIL`, `_tail`, `_alfworld_views`, `_cut` (called by `_slices`; held-set lines untouched), `_items_of`
  (SQ tail ids), `_blocks` (ALF whole rooms in the seeded `supply.room_order`, not sorted room names),
  `_options_only`/`_round_tasks` (J7 probe cells options-only); imports `hashlib`, `digest`, `exclusion`.
  supply.py `VIEWS_KIND`, `FRESH_PART`, `views_record`, `alfworld_pool`. examiner.py `shortcut_public` factored out
  of `shortcut_variant` (behaviour-preserving; shortcut tests pass).
- New tests tests/test_execskill_fivebench_step.py: 7 tests (SQ run on pool + accept on kept tail; tail refused
  without pin/bound exclusion; LM cut incl. 64 probe; J7 accept unit registers the probe as accept_probe and sends it
  options-only; ALF pool = fresh supply with views of the pinned runtime; ALF step room groups + whole-room blocks;
  ALF step refuses games without a view of the pinned runtime).
- Targeted runs (18:3x/18:4x): fivebench_step + supply + exclusion + examiner 38 passed; acceptance + shortcut_sb 34
  passed; step 10 passed / 4 failed -- the 4 failures (test_step1..., a_step_ending...[blocked_twice], c7e_1...,
  pr_c12_1...) come from M2a's #9 (`examiner.sufficient`: fake sets < 30 items are now insufficient_material, never
  admitted; KeyError pass_rate); M2a's area, noted in the coordination log, not fixed here. Before #9 landed the step
  file passed 14/14 with my edits.
- Mutations 102-107 appended; each site occurs once; checked on a throwaway copy that each mutation makes its named
  test fail and the unmutated copy passes (ALL OK).
