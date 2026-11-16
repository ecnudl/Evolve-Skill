# fix-c: fixes from review round C (batch 3)

Step id: fix-c. Base: `git diff de7346c` (batches 1 and 2 at de7346c; this batch's work uncommitted on top). Reviewer
findings: coord-rp15, rc-plan-1, rc-readout-1..7, F1, F2. Abbreviations as in the task: T = skillopt/execskill/typed,
C = T/chain.py.

## Plan (checklist)

- [x] 0. Whole typed suite green before any fix (baseline run: 707 passed in 80.20s)
- [x] coord-rp15 (must-fix): C.members_of includes routed members (RP15); record source/routed and the routed gate-item count; tests
- [x] rc-plan-1 (minor): replay "second error" decided from the previous recovery outcome (R44 d), not from the whole failure history; test error X, equal, restore, error X pauses
- [x] rc-readout-1 (must-fix): economy CL table S0 := C under base_card historical; header, definitions, docstring; test
- [x] rc-readout-2 (must-fix): identical-requests terms are noise samples, not measured effects (CL table, RP4 maximum, macros, 5x5 alias rows); tests econ2/econ3 shapes
- [x] rc-readout-3 (must-fix): generalization view labels routed benches from mount.type, not only sources; definitions; test
- [x] rc-readout-4 (minor): _diff_cell checks same class before the alias mark
- [x] rc-readout-5 (minor): _rp4 prints missing (pending/invalid) earlier terms
- [x] rc-readout-6 (minor): related-gain table prints the whole-slice home gain, fired gain apart
- [x] rc-readout-7 (minor): terminal summary read counts = readout.read_counts
- [x] F1 (must-fix): read-plan T7 (label neutrality) in tests/typed2_bound_driver.py and tests/test_typed2_machinery.py
- [x] F2 (minor): fresh-unit resume test proves finished cells are not sent again
- [x] Final: whole typed suite green (718 passed in 83.52s; 707 before + 11 new tests)

## Done (per finding: verdict, change, evidence)

### coord-rp15 -- fixed (must-fix; addendum RP15)

- `C.members_of` (T/chain.py:1419) now returns the earlier benches with a source in the home type T (`member`
  'source') PLUS every other earlier bench with at least one gate item that the step's type map routes into T
  (`member` 'routed'); each row carries `routed_gate_items` (the number of the bench's gate items routed into T, for a
  source member too). New `C.routed_gate_items` (T/chain.py:1437): `TypeMap.assign` on each gate item's practice vector
  (`vectors_of`, the vectors every mount routes with), zero model calls; it returns 0 without embedding when the
  bench's source has another structural signature (no item of it can reach T: a practice source has one signature).
  Benches not learned yet are never members (only `order[:k-1]`).
- Records: `member_outcomes` carries both fields; `C.shared` puts `{bench, source, member, routed_gate_items}` in every
  `shared_with` row of a card or program decision; `decisions.json['shared_type']` rows carry them too (T/chain.py:1945).
  `gates.recompute` is unchanged (it reads only `bench` of `shared_with`) and reproduces every record in the new tests.
- Readout: `_decision_row` keeps `shared_with` as bench names and adds `membership`; `_related_row` and `_md_related`
  print the member kind, e.g. `searchqa (routed: 1 gate item)` (T/readout.py:207, :238, :1749).
- Tests (tests/test_typed2_shared.py, through the REAL mount, writers and reads):
  `test_a_split_bench_with_gate_items_routed_into_the_home_type_is_a_routed_member[hold|harm]`: OfficeQA's no-harm
  check in SearchQA's type fails, so it opens t02; SearchQA's gate item g0 is embedded in OfficeQA's cluster
  (exact-axis embedder), so the step routes it into t02. SearchQA becomes a routed member with
  `routed_gate_items` 1; its block reaches the card writer; the card is checked on SearchQA's WHOLE gate slice (g0
  mounts the candidate in t02, g1/g2 keep t01 and arm F: `candidate.applied` False); 'hold' is accepted, 'harm' is
  rejected `member_harm`; recompute reproduces every record; the readout shows the kind and count.
  `test_a_split_bench_with_no_gate_item_routed_into_the_home_type_is_no_member`: the same chain without the routed item:
  no member, no member unit, no `shared_with`, no member block.
- Fails before: /tmp/typed2-neutral/fixc/before_rp15.py runs the three tests with the old `members_of`: both routed
  cases fail (`KeyError: 'shared_type'`, no member), the control passes before and after.
- Pin moved on purpose: `test_a_card_that_gains_at_home_and_regresses_on_the_member_is_rejected_member_harm` asserted
  `shared_with == [{'bench', 'source'}]`; it now expects `{..., 'member': 'source', 'routed_gate_items': 3}`.
- Unchanged: every request, cell and unit of the golden scenarios (`GOLDEN_RUNS` of test_typed2_base.py and the 5w
  goldens of test_typed2_shared.py): there no earlier gate item routes into another bench's type, and the new fields
  live in decision records only.

### rc-plan-1 -- fixed (minor; R44 d)

- `C.replay_plan` (T/chain.py:1017): a replay ERROR now voids the plan only when the previous recovery outcome was a
  replay error with the same code: the last applied recovery was for `read_plan_changed`, has no replay outcome yet, and
  the pause it resolved carried this very detail (new `C.last_recovery_detail`, T/chain.py:1033). An older error that a
  later replay resolved is no first strike any more. `replay_different` keeps its rule (`detail in failures`; R44 c).
- Test (tests/test_typed_readplan.py):
  `test_a_replay_error_after_an_equal_replay_and_a_restored_plan_is_a_first_strike_again`: replay error `timeout` ->
  recovery -> equal -> reads settle aliases and stop inside C0's fresh unit -> the plan file is edited -> pause
  `plan_file_mismatch` -> the recovery restores it -> the check replay errs `timeout` again: it now PAUSES
  (`paused_again`), every settled alias kept; the next recovery reads on with an equal replay, never void. Outcomes
  `[(1, replay_equal), (3, plan_restored), (3, paused_again), (4, replay_equal)]`.
- Fails before: /tmp/typed2-neutral/fixc/before_rcplan1.py with the old rule: "the restored plan was voided by an old,
  resolved replay error"; the existing `test_a_replay_error_pauses_and_the_same_error_again_voids_the_plan` passes
  under both rules.

### rc-readout-1 -- fixed (must-fix; D17)

- `_bench_metrics_economy` / `_cl_economy` (T/readout.py:1350, :1411) take S0 := `BASE_EVENTS[base_card]` (C under
  'historical', C0 under 'format'): forward_transfer = acc(S_{k_b-1}) - acc(S0), plasticity at k_b = 1 = acc(S1) -
  acc(S0). gain_over_C0 and gain_over_C unchanged; the full-mode typed-v1 `_formulas` unchanged (its tests pin them).
  Header ("S0 := C, the start of learning"), `definitions['S0']`, `definitions['formulas']`, the module docstring and a
  new "- terms:" line under the CL table updated.
- Test: `test_economy_terms_start_from_the_base_row_C_under_historical` (T20 fixture econ1): officeqa forward transfer is
  structural '-' (S1 in C's class), searchqa plasticity is S1 - C = +25.0; with the state's base set to 'format' the
  same forward transfer is S1 - C0 (measured +25.0). Before (the reviewer's render of econ1,
  /tmp/typed2-neutral/rc-readout/econ1/run/readout/19700101T000000Z/readout-G.md lines 337-338): officeqa forward
  transfer +25.0, searchqa plasticity +50.0.

### rc-readout-2 -- fixed (must-fix; R67, R70)

- `_term` (T/readout.py:1277): a same-phase term between two fresh units whose requests are identical on every item
  (R67, first inputs) is kind `noise_sample`, value null, its reading as `reference` (by construction 0, as a structural
  term).
- `_rp4` (T/readout.py:1304): such an earlier event is a by-construction term (`noise_terms`, listed with its reading),
  never the maximum. `_macro_terms`: noise samples enter column (a) as 0 and never (b); `noise_samples` counted and
  printed. 5x5 alias rows carry the contrast cell they stand for (`shown`), so the label prints (`=S5 +25.0 noise
  sample u/i/c 0/0/0`).
- Markdown: `- (noise sample, ref -25.0)`, `- (4 by-construction terms, of which 1 noise sample: S2 ref +25.0)`,
  `+12.5 (1 of 4 structural, 1 noise sample as 0)`; legend, `CELL_KINDS` and definitions (`noise_sample`) added.
- Test: `test_identical_request_terms_are_noise_samples_in_the_terms_maxima_macros_and_alias_rows` with the econ2 and
  econ3 shapes of the review (monkeypatched OUTCOMES / FALLBACK of the T20 fixture). Before (rc-readout.md finding 2;
  renders under /tmp/typed2-neutral/rc-readout/econ2, econ3): forgetting +25.0, backward transfer -25.0, alfworld gain
  vs C +25.0, 5x5 rows 1-4 `=S5 +25.0` without the label.

### rc-readout-3 -- fixed (must-fix; labels only)

- `_generalization` / new `_routed_into` (T/readout.py:1438, :1449): a non-home bench without a source in the home type
  is `routed` when the fresh unit standing for (S<k>, bench) (its own, or its representative's: same requests) routed
  n > 0 of its N panel items into the home type (`mount.type` of the projected cells); printed `(routed n/N)`;
  `routed_items` / `items` in the JSON. Same-type stays source-based; `other-type` otherwise. Definition and footnote
  updated.
- Test: `test_the_generalization_view_labels_a_bench_routed_into_the_home_type` (T20 fixture with the S2-officeqa cells
  routed into t01: officeqa at S1 is `routed 4/4`, at S3 `other` with 0/4). Before: always `other`
  (`test_generalization_view_marks_home_same_type_and_other_type_benches` still asserts that on the unmodified fixture).

### rc-readout-4 -- fixed (minor)

- `_diff_cell` (T/readout.py:1252) computes the contrast first: inside one class `-` whatever the row's source;
  otherwise the alias cell carries `shown` (value, kind, requests label) and `_fmt` prints it after `=X` (`split`, a
  value, or a noise sample).
- Test: `test_a_5x5_alias_row_inside_one_class_is_a_dash_and_otherwise_prints_its_representatives_contrast` (zebralogic
  rows 1-2 of S<k> - C0 and officeqa row 1 of S<k> - C print `-`; no `=S3 —`). Before: `=S3 — u/i/c 0/0/0` (econ1 render
  lines 290-291 of the S<k> - C0 matrix).

### rc-readout-5 -- fixed (minor)

- `_rp4`: an earlier event without a reading (pending, invalid, void_alias) makes the maximum `incomplete` (value null,
  `partial` = the maximum of the others, `missing_terms` = [{event, source}]); printed
  `incomplete [missing: S4 pending; max of the others -25.0]`; the macros count it as pending.
- Test: `test_a_maximum_with_a_missing_earlier_reading_is_incomplete`. Before: zebralogic forgetting `-25.0`
  (econ1 render line 339).

### rc-readout-6 -- fixed (minor)

- `_md_related` (T/readout.py:1759): `home gain pts` is the whole-slice gain (a program's `whole_slice_mean_points`, a
  card's gain); a new `home fired gain pts` column holds a program's fired-items gain; a footnote says the compared
  columns are whole slices. Test: `test_the_related_gain_table_compares_whole_gate_slices` (program +50 fired / +2
  whole slice: home gain +2.0, fired +50.0). Before: `home gain pts` = `mean_points` = the fired gain.

### rc-readout-7 -- fixed (minor; ops display)

- `run_typed.read_counts(state, chain_dir=None)` / `state_summary(state, chain_dir=None)` (scripts/run_typed.py:241,
  :269): with the chain directory an economy chain's counts are `readout.read_counts(readout._resolve_chain(chain_dir,
  state), state)`, the numbers `status` and the readout print; `run` and `smoke` pass their chain directory
  (`_chain_dir`, :343; the smoke's is `<root>-smoke/<chain>`; None when absent). Without a directory the state-only
  counts are kept (their test unchanged; no command prints them now).
- Test: `test_the_terminal_read_counts_are_the_readouts` (econ1: fallbacks 2, voided aliases 5, equal to `status`).
  Before: `state_summary` had no directory argument and printed fallbacks 1 / void aliases 4 / fresh_planned None for
  the same state (rc-readout.md finding 7).

### F1 -- fixed (must-fix; read-plan T7, R14)

- tests/typed2_bound_driver.py: new case `label` (`label_case`, `RecordingWorker`): one SearchQA state whose type offers
  a program with `applies` and a note-writing `before_call` (the driver's HOOKED), mounted (arm F, base historical, the
  selector picking it) and solved through the real `mount.solve` and the bound shell, router, package and client code
  under the read units `test-read-S3-searchqa` and `test-read-S5-searchqa`. The recording fake worker records the load
  request the bound client itself would send (`client._entries`, `client._load_request`) and every hook call with its
  argument hash, and runs the hook in process. Mode 'test' (a fixture procedure needs a fixture package).
- tests/test_typed2_machinery.py (`test_bound_interpreter_runs_every_area_on_the_snapshot`): the program is enabled and
  fires under both labels; hook calls `[applies, before_call]`; the note is in the first request; selection requests,
  hook argument sequences and the solver request hashes of every send are equal; one load request each, equal except
  `package_sha256`, which is each unit's own package hash and differs; nothing written to the scratch. It passes on
  the Mac stand-in snapshot.
- Sensitivity: /tmp/typed2-neutral/fixc/label_negative.py plants a label leak into the request (step label appended to
  the card) and into a hook argument (package hash in the routing view): `sends_equal` False, resp. `hooks_equal` False.
- On dl: the same case runs in the bound driver run before the smoke (impl/7g.md's ops step); it must end with stage
  'done' and pass these assertions (R14: T7 must pass before the smoke).

### F2 -- fixed (minor; test only)

- `test_a_stop_inside_a_fresh_unit_resumes_without_sending_a_finished_cell_again` keeps its assertions and adds: the
  resume sends exactly one solver request on `practice-read-S5-searchqa` (= the cells missing at the stop) and only
  solver / selection requests there, and every cell file written before the stop is byte-equal after the resume.
- Sensitivity: /tmp/typed2-neutral/fixc/before_f2.py makes the resume re-solve the finished cell (its unit treated as
  new): the old assertions pass, the new `resent.count('solver') == ... == 1` fails.

## Tests

- Whole typed suite, Python 3.13 (the task's command):
  `mkdir -p /tmp/typed2-neutral && cd <repo-root> && TMPDIR=/tmp/typed2-neutral
  <python> -m pytest -q -p no:cacheprovider tests/test_typed_*.py tests/test_typed2_*.py`
  -> `718 passed in 83.52s (0:01:23)` (baseline before any fix: `707 passed in 80.20s`).
- The touched test files under Python 3.10 (`<python>`; no 3.11 on this Mac):
  tests/test_typed2_shared.py tests/test_typed_readout.py tests/test_typed_readplan.py tests/test_typed_cli.py
  tests/test_typed2_machinery.py -> `136 passed in 55.86s` (the bound driver, with the new T7 case, ran under 3.10).
- New tests (11): test_typed2_shared.py 3 (RP15), test_typed_readplan.py 1 (rc-plan-1), test_typed_readout.py 7
  (rc-readout-1..7). Strengthened: test_typed2_machinery.py::test_bound_interpreter_runs_every_area_on_the_snapshot
  (F1, T7) and test_typed_readplan.py::test_a_stop_inside_a_fresh_unit_resumes_without_sending_a_finished_cell_again
  (F2). Before/after evidence: the scratch scripts named per finding above (before_rp15.py, before_rcplan1.py,
  before_f2.py, label_negative.py under /tmp/typed2-neutral/fixc/) and, for the readout, the reviewer's own renders of
  the pre-fix code under /tmp/typed2-neutral/rc-readout/econ1..3.

## Choices

- RP15: `routed_gate_items` is recorded for source members too (the decision record "lists, per member, ... the number
  of its gate items routed into T"); benches of another signature are skipped without embedding. Routed members get
  everything D16 gives a member (writer block, member outcomes, member base and checks), because `members_of` is the
  one member set M of D16 (a) and (b) and RP15 widens it; the member check stays on the whole gate slice (RP15).
- rc-plan-1: only the replay-ERROR rule changed (R44 d); `replay_different` keeps `detail in failures` (R44 c).
- rc-readout-2: a noise-sample term has value null and its reading as `reference` (the reviewer's shape, like `split`);
  it counts as a by-construction term in RP4 and enters macro (a) as 0, never (b), and is counted apart
  (`noise_samples`): an identical-request contrast has expectation 0 by construction, exactly like a structural term.
- rc-readout-3: the routed share is counted on the cells of the fresh unit that stands for the pair (the pair's own, or
  its representative's, which sends the same requests); no sealed identities file is opened. A type-map-only
  difference between the event and its representative can move an item's type id without changing its request; such
  an item carries no skill of the home type, so the label never hides a request change.
- rc-readout-5: the reviewer's "refuse a maximum" option (R74: pending / invalid shows no value), with the partial
  maximum and the missing events printed beside; the plan's class is not used for missing pairs (a voided or invalid
  alias's planned class is exactly what is in doubt).
- rc-readout-7: `chain_dir` is optional, so a bare state (its existing test) keeps the state-only counts; no command
  prints those any more.
- F1: the T7 case runs in mode 'test' (a fixture procedure needs a fixture-evidence package); the recording worker
  runs the hook in process: the container side (the bound `worker_v222.py` keeps only `loaded` / `limits`) stays the
  [V] fact of R14; the case proves the host side, which is everything the label could reach besides the container.

## Disagreements

- RP15 and the writers' D16 sentence: `writers.MEMBERS_MEANING` / `engineer_prompt.MEMBERS_MEANING` (pinned in
  `SENTENCE_SHA256` and the machinery's TEXT_PINS) tell the writer that the card or program also reaches "every task of
  the other sources of this task type". For a routed member only its routed tasks get it, and most of its learn-slice
  examples mount another type. I left the pinned sentences unchanged (a change of the writer requests and pins is a
  coordinator decision). Options: (a) keep (the gate on the whole slice is what protects the member); (b) a
  routed-member variant of the sentence (new pins); (c) routed members in the gate only (no writer block).

## Left for later steps

- Ops on dl, before the smoke: the bound driver run of impl/7g.md now also runs the T7 case (`cases.label`); it must
  pass there (R14: T7 must pass before the smoke). The Linux suite alone under Python 3.11.
- Coordinator: the RP15 writer-sentence question above.
- Observation outside this round's findings (not changed): after a restored plan, R44 c says the check replay voids
  on `different`; `replay_plan` pauses on a first `different` there and voids only on the next one (one more owner
  pause, no extra paid read).
- A `full` root under base 'historical' keeps typed-v1's S0 := C0 formulas (`_formulas`, unchanged on purpose and
  pinned); the configured typed-v2 run reads under `economy`, whose terms now start from C.
- The living documents (docs/current-workflow.md, docs/results-and-lessons.md) are not edited by this step, as by the
  other steps of this batch; the coordinator updates them with the batch.
