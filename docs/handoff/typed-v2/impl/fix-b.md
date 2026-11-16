# fix-b: resolution of the review-b findings (Steps 1 to 5)

Status: all twelve ids resolved (10 fixed, 2 deferred, 0 refuted). Each id is resolved as fixed (with a test that
fails before and passes after), refuted (with file:line evidence) or deferred (with the step it belongs to).
`T/` = `skillopt/execskill/typed/`.

## Checklist

- [x] coord-1 (must-fix) engineer_prompt [import] row: from-import of a banned member -- fixed
- [x] rb-stats-1 (minor) members_of only counts benches whose source is in T -- deferred (coordinator / owner: D16 member set)
- [x] rb-stats-2 (minor) markdown readout omits se_points_fired / se_points_scaled -- fixed
- [x] rb-requests-F1 (must-fix) 'format' golden no longer tied to cdf85b6 -- fixed
- [x] rb-requests-F2 (minor) program_payload member loop ignores trajectories_omitted bytes -- fixed
- [x] rb-resume-1 (minor) SIGINT in a main-thread cell call leaves reruns 0 -- fixed
- [x] rb-resume-2 (minor) card writer / describer recorders overwrite earlier sends -- fixed
- [x] rb-resume-3 (minor) rerun_cells mutated outside ledger.lock -- fixed
- [x] rb-resume-4 (minor) smoke command cannot be resumed -- fixed
- [x] F1 (minor) `--base-card historical` missing from the ops hand-off list -- deferred (Step 7 hand-off; coordinator)
- [x] F2 (minor) readout does not show base_card / D17 sentence -- fixed
- [x] F3 (minor) prepare summary does not print machinery_code -- fixed

## Notes per id

### coord-1 -- fixed

Reproduced on the real screen (`policy._imports` + `_forbidden_member`, `X/policy.py:445-458`): `from datetime import
time`, `from pandas import read_csv`, `from numpy import random` each give one `import` violation, while the [import]
sentence (DESIGN 3.2 verbatim) called every `from M import name` allowed. Not a change of a decision: D3 requires the
prompt to state the rules the bound screen enforces; the DESIGN wording did not, and the coordinator ordered the fix.

Change (`T/engineer_prompt.py`): `PROMPT_VERSION` `typed-engineer-prompt-2`; new `IMPORT_MEMBER_EXAMPLES` (the three
lines) and `IMPORT_MEMBER_LEGAL`; the [import] sentence gains, before `No "import *"`: `In "from M import name" the
name must not be one that the [name] or [attribute] rules below ban, nor a blocked module name (random and time
included): "from datetime import time", "from pandas import read_csv" and "from numpy import random" are rejected.`
(`random and time` rendered from `policy.ORDINARY_ATTRIBUTES`); the rewrite becomes `leave type hints out or use the
built-in names (list, dict); for a banned member import the module and write the member after a dot where the
[attribute] rule allows it (import datetime, then datetime.time).`; `verify()` also runs the three lines (rejected
with rule `import`, mapped to the row) and the legal form (passes) through the real screen; the ten `PINS` moved.
The frozen `policy.check` call is unchanged. Texts are 402 characters longer (10,478 to 11,618).

Tests (`tests/test_typed_engineer_prompt.py`): new `test_import_row_names_the_banned_member_forms_the_real_screen_rejects`
(the three lines through the REAL `policy.check`, the legal form, one example of each banned kind) and
`test_verify_raises_when_the_screen_stops_rejecting_a_named_import_example`; pins, version and lengths updated;
`test_texts_are_the_design_wording` still compares every byte with DESIGN 3.2, the [import] line through `coord1()`
(DESIGN's line plus exactly the inserted sentence and the new rewrite).

### rb-requests-F1 -- fixed

Confirmed: `test_format_base_sends_every_request_and_cell_of_cdf85b6` compared with `GOLDEN_RUNS`, re-pinned by 5w and
5x to their own output. Fix (option 1 and option 2 together):
- `tests/typed2_format_driver.py` (new, not a test module): the one-bench scenarios (`smoke-single`,
  `default-single`; OfficeQA opens its own type) as code that runs on this tree in process or, as a script under
  `python -I`, on another tree's typed package.
- `tests/test_typed2_base.py`: `CDF85B6_FORMAT_IDENTITY` (distinct `[purpose, sha256(system NUL user)]`, n and
  digest) computed from `git archive cdf85b6` (paths `CDF85B6_PATHS`); measure `format_identity` with two documented
  normalizations: `undo_coord1` (the coord-1 wording mapped back) and `card_points` (round-2 `result` gain numbers at 9
  decimals, DESIGN 4.2 (2)). The smoke value equals the review's own cdf85b6 measurement (`323f1e33...`).
  `test_format_base_one_bench_requests_are_cdf85b6s` (this tree, in process) and
  `test_format_base_cdf85b6_pins_are_rederived_from_the_commit_live` (the commit, fresh interpreter; skips without git
  or the commit, as the typed-v1 writer blob test does). The old test is renamed
  `test_format_base_sends_every_request_and_cell_of_the_5x_tree` and says what it pins.
- The goldens `GOLDEN_RUNS` (5x) and `GOLDEN_SINGLE` (5w) keep their values: they compare with the coord-1 wording
  mapped back (requests; request hashes in decision records through `coord1_hashes`) and assert that the mapping
  touched program-writer requests only, and every request carrying one of the ten texts.

### rb-requests-F2 -- fixed

Reproduced with the review's probe (`/tmp/typed2-neutral/rb-requests/fitedge.py`): bound = size after one member drop
+ 5 gave home trajectories 2 -> 1 with one member trajectory left. `W.program_payload`'s member loop now measures
`{**payload, 'trajectories_omitted': 0}`, the message `fit` measures first; the probe now gives home 2 (none omitted),
member 0 (2 omitted). The loop runs only for a shared type, so no request of a one-bench type changes (goldens
unchanged). Test: `tests/test_typed2_shared.py::test_program_payload_fits_member_trajectories_as_fit_measures_the_message`
(fails before: `(1, 1) != (0, 2)`).

### rb-resume-1 -- fixed

Reproduced: a KeyboardInterrupt inside the first (main-thread) solve call of `s1/card-r1` / `s1/noise` was settled in
`CallRecorder`'s `finally` (pending `{}`), so the resumed cell had no recovered row and `reruns` stayed 0 while R + 1
requests went out. Fix (`T/units.py` `CallRecorder.__call__`): a `BaseException` that is no `Exception`
(KeyboardInterrupt, SystemExit) is recorded in the send (`exception`) and the call is NOT settled; its reservation
stays pending exactly as after a kill, so `Ledger(resume=True)` turns it into a `recovered` row and a `(unit, cell)`
rerun entry, and `chain._Run.reruns` counts it. An ordinary exception still settles at the bound (unchanged). Tests:
`tests/test_typed_units.py::test_an_interrupted_call_stays_pending_and_is_recovered_on_resume` (KeyboardInterrupt,
SystemExit) and `tests/test_typed2_gate.py::test_a_sigint_inside_a_gate_cell_is_sent_again_and_counted_as_a_rerun`
(`s1/card-r1`: `reruns == {'baseline': 0, 'candidate': 1}`; `s1/noise`: `reruns == 1`; the interrupted cell sent
twice, every other once). Both fail before the fix (no pending entry).

### rb-resume-2 -- fixed

Confirmed: `C.cards` and `C.describe` built a fresh recorder on the same calls file. Both now wrap the role call with
`_keep_earlier_sends` (as `programs` does), so every send of every attempt stays in `calls/writer-card_writer.json`
and `calls/describe-<id>-describer.json`. The writers never read `call.sends` (grep), so the requests and records do
not change. Test: `tests/test_typed2_gate.py::test_a_resumed_card_writer_or_describer_keeps_every_earlier_send_in_its_calls_file`
(both purposes; fails before: 1 send in the file instead of 2).

### rb-resume-3 -- fixed

Confirmed: `mark_infrastructure_reruns` (`.add`), `reads._read` and `C.cells` (`difference_update` in `finally`)
changed `ledger.rerun_cells` without `ledger.lock` while `run_unit` iterates it. Fix: `units.Ledger` gets three
locked helpers, `mark_rerun`, `reruns_of_unit`, `consume_reruns`; every other access in `T/` goes through them.
Tests: `tests/test_typed_units.py::test_rerun_entries_are_marked_read_and_consumed_only_under_the_ledger_lock` (a
guarded set that refuses any access without the lock: fails before on `.add`),
`::test_no_code_of_the_typed_package_touches_rerun_cells_outside_the_ledger` (AST: before, 5 sites outside the
Ledger), and `tests/test_typed2_gate.py::test_parallel_read_units_and_learning_units_touch_rerun_entries_only_under_the_lock`
(a whole fake chain with the real parallel read units on the guarded ledger).

### rb-resume-4 -- fixed

Confirmed: `run_typed.py smoke` had no `--resume` (argparse exit 2) and `run` refuses a smoke state. Fix
(`scripts/run_typed.py`): `smoke --resume`, passed through `_smoke_run` to `smoke.run(resume=True)` only when given
(the call shape without it is unchanged); the owner's recovery.json stays required (`chain.recover`). Test:
`tests/test_typed_cli.py::test_a_paused_fake_smoke_resumes_through_the_command_line_and_sends_no_finished_call_again`
(a card-writer fault pauses the fake smoke, exit 5; without recovery.json the resume is refused; with it the smoke
completes, exit 0, with exactly one send more than a smoke that never paused).

### F3 -- fixed

`scripts/run_typed.py prepare` now prints `machinery_code` beside `base_card` (spec/identity.md 1.10). Tests:
`tests/test_typed_cli.py::test_prepare_prints_the_sealed_machinery_record_for_the_launcher` (new) and the extended
summary of `test_run_smoke_prepare_go_through_the_adapters`.

### rb-stats-2 -- fixed

Confirmed: `readout._md_step` printed fired n, the fired gain, the whole-slice SE and tau, not `se_points_fired` /
`se_points_scaled` (the JSON row had both, `readout._decision_row`). The markdown decision table gains the columns
`SE fired pts` and `SE scaled pts` (a dash for card, no-harm and member rows). Test:
`tests/test_typed_readout.py::test_the_markdown_step_table_shows_both_informational_SEs_of_a_program` (fails before:
no such column).

### F2 -- fixed

Confirmed: no `base_card` in the readout. `readout.chain_readout` stores `base_card` from the chain state (the state
holds the manifest's sealed value; `_open_state` refuses a resume with another base; the closed readout's data
boundary stays the chain directory). The markdown header says `- base card: historical (sealed `base_card`): ...` with
D17's statement (learned arms compose on C; a bench whose type learned nothing reads exactly C; the C row is the start
of learning, not learned gain; typed-v2 starts from C, the v2.24 SkillOpt / GEPA baselines from an empty skill, read
2026-11-07/08, cross-run, cross-date), or the 'format' line, or `not recorded`; in open mode the base row of every
panel is labelled `C (base of S1..S5)` ('historical') or `C0 (base of S1..S5)` ('format'). Test:
`tests/test_typed_readout.py::test_the_readout_shows_the_sealed_base_card_and_the_base_row` (three bases; fails
before: no `base_card` key).

### rb-stats-1 -- deferred (coordinator / owner decision on D16's member set)

The finding is right about the code and the spec gap: `C.members_of` (`T/chain.py`, "shared types" section) takes
the earlier benches whose practice SOURCE is in the home type, D16's literal definition ("the earlier benches b' with
a source in T"), while `tasktypes.TypeMap.assign` (`T/tasktypes.py:222-236`) routes an item to the nearest TYPED
source among all sources with its signature, so an earlier bench's items can route into a later bench's type without
it being a member. Either remedy changes what D16 decides (the member set, hence which units run and which candidate
is accepted) or adds a record D16 does not define; F14's wording ("benches of other types get byte-identical
requests") lives in the addendum, which this step may not edit. Exposure in this bench order: only SearchQA and
OfficeQA share a signature (`question/context`), and only when OfficeQA's no-harm merge into SearchQA's type fails
(it then opens its own type with that signature). For the coordinator: (a) the zero-call superset ("earlier benches
with at least one gate item that `typemap.assign` routes to T after typing") would be a small change in
`C.members_of` plus tests, a 5x follow-up; (b) the cheaper exposure count (per earlier bench, how many of its gate
items route to T) would be a record field for the readout.

### F1 -- deferred (Step 7 "Handed to operations"; the coordinator's ops list)

Correct: `--base-card` defaults to 'format' (D17 keeps that code default for the golden tests) and IMPLEMENTATION-ORDER
Step 7 hands `prepare` to operations with `--memory-lock unit_shared` only. The fix is an operations item, not code:
(1) the coordinator's ops list (addendum) and Step 7's hand-off add `prepare --base-card historical` for the run root
and `prepare --smoke --base-card historical` for the smoke root; (2) the ops launcher (`run-typed.sh`, ops side, not in
this tree) stops after each `prepare` unless the printed `base_card` is `historical` and, now that F3 prints it, unless
the printed `machinery_code.bound` is true (spec/identity.md 1.10). Changing the code default would change D17 and is
not done. The printed `base_card` (5b) and `machinery_code` (F3, this step) give the launcher what it checks.

## Before / after evidence

The new tests were run in a copy of this tree whose seven changed code files were the pre-fix ones (kept in
`/tmp/typed2-neutral/fixb-orig/`; `engineer_prompt.py` rebuilt by reversing the coord-1 edit): 22 failed, 1 passed.
Failing there: the two coord-1 tests and the DESIGN-wording test; the F2 payload test; the interrupted-call tests (2
units, 2 chain); the calls-file tests (2); the three rerun-lock tests; the two new CLI tests and the extended adapter
test; the readout tests (1 + 3). The cdf85b6 anchor test failed there only on its coord-1 assertion: its identity
already matched the cdf85b6 pins before fix-b (the requests were cdf85b6's, as the review measured). The one test that
passed there is the measure's sensitivity check (`test_format_identity_sees_one_changed_request`), which depends on no
fix. On this tree the same tests pass.

Suite: `tests/test_typed_*.py tests/test_typed2_*.py` -> 552 passed (Python 3.13.12, final run 29.5 s); the same 552 pass
under Python 3.10.20 (`<python-env>`), including the live re-derivation of the cdf85b6 pins.

## Files changed by fix-b

Code: `T/engineer_prompt.py` (coord-1), `T/writers.py` (F2), `T/units.py` (rb-resume 1, 3), `T/chain.py`
(rb-resume 2, 3), `T/reads.py` (rb-resume 3), `T/readout.py` (rb-stats 2, F2), `scripts/run_typed.py` (rb-resume 4,
F3). Tests: `tests/test_typed_engineer_prompt.py`, `tests/test_typed2_base.py`, `tests/test_typed2_shared.py`,
`tests/test_typed2_gate.py`, `tests/test_typed_units.py`, `tests/test_typed_cli.py`, `tests/test_typed_readout.py`;
new `tests/typed2_format_driver.py` (not a test module). Nothing outside `T/`, `scripts/run_typed.py`, `tests/` and
this report; no existing test deleted or weakened (pins that moved with coord-1 are updated and every byte stays
checked).

## For the coordinator

- coord-1 deviates from DESIGN 3.2's verbatim [import] sentence and from `PROMPT_VERSION = 'typed-engineer-prompt-1'`
  (DESIGN 3.2, 4.3, spec/engineer.md) by your order; Step 7's check 6 pins the new `PINS`.
- rb-stats-1 needs your decision on D16's member set (and F14's wording); options above.
- F1 needs the ops hand-off: `prepare --base-card historical` for both roots and the launcher's stop on the printed
  `base_card` and `machinery_code.bound`.
