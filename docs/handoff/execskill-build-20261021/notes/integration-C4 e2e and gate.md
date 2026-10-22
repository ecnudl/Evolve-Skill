# Integration C4 (e2e and gate): gate (iii), the C4 fixes and the ticket ledger

Integrator C4, 2026-10-22. Protocol `fivebench-execskill-v1`. I read every builder note (A1-A13, C1-C5, fixer), the
five earlier integration notes (B1-B5) and all 42 tickets, ran the whole route-B suite on dl, fixed the mismatches
below, and ran gate (iii) in a fresh copy of the working tree.

How the work was done:
- No model call. No credential file or `.env` opened or printed. No test-pool data read (fixtures are synthetic).
- No state-changing git command. No frozen file edited (`skillopt/coevo5`, `skillopt/continual_eval`,
  `scripts/run_coevo5.py`, `scripts/weak_solver_probe.py`, the scorers). No `.pyc` written into either tree.
- Edits were applied on dl by two patch scripts (fixes 1-5, then fix 6). Each checks every replacement site first
  (exactly the expected number of occurrences) and then writes each file whole (temporary file + rename), so no file
  was left half written.
- Everything here is an engineering fixture on fakes (`engineering_fixture`). Nothing here is evidence of a method
  effect.

## Gate (iii): PASSED on a fresh copy of the working tree, with three caveats

| Gate item (plan §9 (iii), §8.2, §8.3) | Result |
|---|---|
| Plan §8.2 e2e test, binding pilot SpreadsheetBench → OfficeQA, chains G and D (`tests/test_execskill_e2e.py`, 11 tests) | pass: `11 passed in 329.32s` in the dev tree after fixes 1-5, and again inside both fresh-copy runs |
| Mutation suite (1)-(30) (`tests/test_execskill_mutations.py`; 31 entries, because (27) has two halves, 27a and 27b) | every mutation makes its named test fail; the unmutated copy passes first |
| Whole route-B suite plus the frozen tests, in the fresh copy | `1013 passed in 512.91s (0:08:32)`, 0 failed: 923 route-B tests plus the 90 frozen tests of `test_coevo5_core.py` and `test_weak_solver_probe.py` (the copy was made again after fix 6) |
| `python -B scripts/run_execskill.py --help` and `<subcommand> --help` for every subcommand, in the fresh copy | 26 runs (the script and its 25 subcommands), every one exit 0, on both copies |
| `smoke-make --dry-run` with fakes, in the fresh copy | exit 0, `written: false`, the smoke root not created, one synthetic item per set (run on both copies; the final copy's dry-run spec sha256 is `32194d74…`) |

The CLI checks ran from a harness outside the tree, `/tmp/integ-c4/gate_cli.py` on dl, with `python -B` and the
launch environment. As in B5, the CLI has no flag for fakes, so the harness replaces `manifest.environment` (which
would run `docker image inspect` and one sandbox ping) with the fake of `tests/test_execskill_cli.py`, and passes
synthetic item sets and a synthetic passing self-test (`tests/test_execskill_smoke.py::selftest`). It prints counts
only and wrote only under `/tmp/integ-c4/smoke-dry`.

Caveats (none of them is a failing test):
1. **A copy, not a `git clone`.** The registered gate says "a fresh `git clone`". The route-B files are untracked, so
   a clone would not contain them. The copy was made with
   `rsync -a --exclude=.git --exclude=__pycache__ --exclude='.env*' /data/execskill-dev/ /data/execskill-clonecheck/`.
   After the main agent commits, the same pytest command must be repeated in a real clone.
2. **The second pilot of plan §8.2 is not built.** Plan §8.2 names SpreadsheetBench → ALFWorld (FakeAlfEnv) as well,
   and says SB → OQ is the binding pilot. Only the binding pilot exists (note C4, deviation 1). ALFWorld's test-read
   routing is covered by `test_execskill_evaluation.py::test_isolation_2`; no ALFWorld learning step runs end to end.
3. **The test read is real for OfficeQA only.** The other four benches' read units are stand-in records (note C4,
   deviation 3), so the readout tables cover OfficeQA only.

## pytest (dl, `PYTHONDONTWRITEBYTECODE=1 /root/continual-alf-prep-20260928/env/bin/python -B -m pytest -q -p no:cacheprovider`)

| Run | Files | Result |
|---|---|---|
| Dev tree, before any edit | `tests/test_execskill_*.py tests/test_weak_solver_probe.py tests/test_coevo5_core.py` | `1010 passed in 503.19s (0:08:23)` |
| Dev tree, after the edits: the touched modules | cli, chain, examiner, exclusion, step, rounds, generators, protocol, budgets | `88 passed in 55.64s` |
| Dev tree, after the edits: the e2e file alone | `tests/test_execskill_e2e.py` | `11 passed in 329.32s (0:05:29)` |
| Fresh copy `/data/execskill-clonecheck`, after fixes 1-5 | `tests/test_execskill_*.py tests/test_coevo5_core.py tests/test_weak_solver_probe.py` | `1012 passed in 516.46s (0:08:36)` |
| Dev tree, after fix 6: generators, examiner, step | three files | `26 passed in 42.90s` |
| Fresh copy, made again after fix 6 (**the gate run**) | `tests/test_execskill_*.py tests/test_coevo5_core.py tests/test_weak_solver_probe.py` | `1013 passed in 512.91s (0:08:32)` |

The fresh copy and the dev tree hold no `.pyc` afterwards. The suite is slow now: the e2e pilot fixture alone takes
about 200 s, so a whole run takes 8-12 minutes.

## What I fixed

1. **Ticket C4-1: G_acc and G_self items of one generator shared item ids.** `examiner.build` numbered every set
   from 0, so `gen:<generator>:0` named a G_self item and a different G_acc item. The band adjustments of one generate
   unit also restarted at 0, so the probe cells of two band rounds named different items with the same id. On
   SpreadsheetBench a band-adjusted build would also have tried to make item folders that the first build had
   already made in the same `generated-G_self` directory (`exist_ok=False`, see fix 6): a `FileExistsError`.
   - `examiner.build(..., start=0, ...)` numbers its items from `start`. `examiner.Generated` gained
     `next_number` (default 0, so existing constructors keep working): the first number the set left unused.
   - `step._build(..., start)`. The generate unit starts its first G_self build at 0 and every band-adjusted build at
     the previous build's `next_number`. It records `numbered` (the final `next_number`) in its result.
   - `step._g_acc` builds G_acc from `generated["numbered"]`. The item id form `gen:<generator>:<n>` (plan §2.5) and
     `examiner.g_acc`'s prefix check are unchanged.
   - Tests: T-EXAM-4 now builds G_acc with `start=built.next_number` and asserts `(4, 8)` and disjoint ids. The e2e
     asserts that every G_acc number is at least `numbered`, which is above every G_self number.
2. **Ticket C2-1 item 2: the CLI could not resume or show a chain's ledger.** Since fixer-5 each chain runs on its own
   ledger (`budgets.ledger_root`: `shared/ledger-G`, `shared/ledger-D`). `resume-ledger` still resumed only
   `shared/ledger`, the smoke's. On a chain run root, the frozen `Budget(...)` constructor creates its directory
   (coevo5/budget.py:121-123), so the command created an empty smoke ledger there and then failed with "not halted".
   A halted chain ledger could not be resumed from the CLI at all. `monitor` had the same blind spot and the same side
   effect.
   - `resume-ledger --root R --chain G|D|smoke --decision TEXT`. `--chain` is required, so the owner always names
     the ledger. A ledger that does not exist is refused and never created.
   - `monitor` prints `ledgers`: the snapshot of every existing `shared/ledger*` directory, by name. It creates none.
   - Tests: `test_resume_ledger_names_its_chain_and_monitor_shows_every_ledger` (new). The parse test passes
     `--chain G`.
   - This is stricter than C2-1 asked (C2-1 proposed a `smoke` default): a resume is an owner decision about one
     ledger, so it should not have a silent default.
3. **Ticket C2-2 item 2: chain G could not go on after an owner's cap raise.** `chain.cap_check` wrote
   `cap-check-G.json` once. A re-check after `Budget.raise_cap` has other content, so the write-once `write_json`
   (continual_eval/core.py:60-61, validator_pilot/api.py:45) raised a ValueError, and the chain crashed instead of
   continuing.
   - A re-check whose record hash differs is now written next to the first as `cap-check-G-<n>.json` (n = 2, 3, ...).
     A restart with unchanged caps rewrites the identical record and pauses again, as before. The pause rule is
     unchanged: any record with `ok: false` pauses chain G.
   - Test: `test_an_owner_raise_lets_chain_g_pass_its_cost_check_again` (new).
4. **Ticket C3-2 item 2: `exclusion.release_path` is public.** The CLI's ALFWorld canary texts used the private
   `_release_path`. Renamed in `exclusion.py` (3 sites), the CLI and `tests/test_execskill_cli.py`.
5. **Stale texts.**
   - `protocol.py`: the `LEDGER` comment now says it is the smoke's ledger and that each chain has its own (C2-1
     item 3).
   - `rounds.py` docstring: the acceptance order is one seeded order per block over every cell, not the unit-blocked
     order (C5-5).
6. **A dropped SpreadsheetBench item crashed the next parameter set (found here; no ticket).** `generators.generate`
   numbers an item `start + len(items)`, so the parameter set after a dropped one gets the dropped item's number and
   id. `sheet.apply` makes the item's folder `out_dir/<sha256(id)[:16]>` with `exist_ok=False` before most of its
   drop checks (`literal_answer`, `edit_target_invalid`, `recalc_failed`, `perturbation_noop`,
   `engine_qualification_failed`). So such a drop followed by another parameter set in the same build raised
   `FileExistsError`, which `generate` does not catch: a real SpreadsheetBench generate unit would have crashed.
   - Reproduced on dl with `/tmp/integ-c4/repro_sheet.py` (outside the tree; one spec, two parameter sets, the first
     dropped after its folder exists): before the fix `raised FileExistsError`; after it one item `gen:g-test-1:0`
     and `{"edit_target_invalid": 1}`.
   - `sheet.apply` now removes the folder it made when the item is dropped. The rest of its body moved unchanged
     into `_made`. The numbering is unchanged, so LiveMath's key letter (`number % 5`, the kept item's running
     number, `generators/livemath.py:167-180`) is unaffected.
   - Test: `test_gen3_a_dropped_sheet_item_leaves_no_folder_for_the_next_parameter_set` (new). The existing drop
     tests used one parameter set per output directory, so they could not see this.
   - The pilot does not reach this path: its SpreadsheetBench step requests no research (note C4, deviation 5).

No other execskill file changed. None of the 31 mutation sites moved: the suite asserts that each site occurs exactly
once, and it passed after the edits.

## Verified against frozen code (mirror at commit 010d453)

- `skillopt/coevo5/budget.py`: :121-123 (`Budget.__init__` creates its root: why `resume-ledger` and `monitor` must
  not build a `Budget` for a ledger that does not exist), :237 `raise_cap`, :331 `halt`, :337-342 `resume` (refuses a
  ledger that is not halted), :344-351 `snapshot`.
- `skillopt/continual_eval/core.py:60-61` `write_json` → `skillopt/validator_pilot/api.py:45`
  `write_immutable_json`: write-once, only a byte-identical rewrite is accepted (fix 3).
- Route-B sites read for fix 1:
  - `generators/__init__.py:55-97`: `generate(..., start=0, ...)` numbers items `start + len(items)`, and the id is
    `gen:<generator>:<number>`;
  - `generators/families.py:145-156`: `generated_item` requires `number >= 0`;
  - `examiner.py:699-723` (line numbers after the edit): `band` requires only that the deciding (last) probe ran on
    items of the final set, so band rounds with distinct ids are accepted;
  - `examiner.py:805-816`: `g_acc` checks the `gen:<generator>:` prefix only.
- Route-B sites read for fix 6: `generators/__init__.py:73` (`number = start + len(items)`, the only `except` is
  `Drop`), `generators/sheet.py:131-132` before the edit (the item folder, `exist_ok=False`, made before the drop
  checks).

## Static check

`ruff check --no-cache` (Mac, the repo's `pyproject.toml`) on the touched files: the edits add no finding
(`generators/sheet.py` and `tests/test_execskill_generators.py`: all checks passed). Five
findings were there before and are not functional: import order (I001) at `examiner.py:48`, `step.py:54` and
`tests/test_execskill_e2e.py:31`, and the pytest fixture re-imports (F811) at `tests/test_execskill_examiner.py:75`,
`:123`. A pyflakes-level pass (`--select F,E9`) over all of `skillopt/execskill`, the CLI and the route-B tests finds
no undefined name; it finds only the same fixture re-imports (F811) in five test files.

## Ticket ledger (all 42 tickets)

"Resolved here" = fixed by this integration. "Owner" = needs the owner's or the registrar's decision, no code can
close it. "Next row" = code still to write, for the next build row (C6: the A13-1 adapters) or the main agent.

| Ticket | Status | Where it stands |
|---|---|---|
| A2-1 | resolved (B1) | solver names, chain D per-bench M and timeouts, one echo set |
| A3-1 | **owner, before S2** | lexicon matching rule (inflections, verbatim quotes); plan §11 item |
| A4-1 | resolved (B1) | `errors.ConsumptionConflict`, stable protocol names |
| A5-1 | **owner/registrar at S0** | sandbox constants stay in `sandbox/client.py`; RLIMIT_AS and the frame cap need S0 measurements |
| A5-2 | decided (registrar 2026-10-22, option 2: per-unit tags); client side done (C5) | the call-site wiring is C5-1 |
| A6-1, A6-2 | resolved (B3) | placebo data shape; how cells call the shell |
| A7-1 | resolved (B2) | shell keys; margin truncation rule in the shell |
| A7-2 | resolved (B3) | verdict, token, judge and item-score wiring |
| A9-1 | resolved (B3, option a) | donor pre-check reports on SpreadsheetBench |
| A9-2 | request 1 resolved (B3); request 2 superseded by the registrar decision of 2026-10-22 (one uniform order per block, J5 re-derived, C5) | whether `rounds.balance` follows is open with C5-5 |
| A9-3 | recipe implemented in `step.py` (C2) and run by the e2e; **MDE constant: owner/registrar** | `decision.json` records `mde_registered: null` |
| A10-1 | **owner/registrar** | engineer/replay/describer constants still in A10's modules; nothing depends on moving them |
| A10-2 | resolved (B4) | donors accept an unanswered last ALFWorld request |
| A10-3 | resolved by contract (B4); the e2e's test read runs a T_F arm | T_F withholds procedures without a description |
| A11-1 | resolved (B5) | `qualify.qualify` signature and record |
| A12-1 | **next row (C6)** | `continuation_check` exists (B5); the manifest adapters do not |
| A12-2 | resolved: `step.py` and T-STEP-1 (C2), e2e (C4) | the SB → ALFWorld pilot is not built (caveat 2) |
| A13-1 | **next row (C6)** | `run`, `terminate`, `step-unit`, `evaluate-unit`, `report` still stop with ConfigurationError naming A13-1 |
| C1-1 | **owner/registrar** | examiner constants into `protocol.py`; values unchanged by a move |
| C1-2 | **owner/A6** | no SpreadsheetBench "no workbook" shortcut view: `examiner.gates` records that shortcut gate as `not_run`, so no SpreadsheetBench generated set can be admitted (the pilot's SpreadsheetBench step requests no research and never reaches the gate) |
| C1-3 | **owner** (confirm the G_acc reading; SpreadsheetBench G_acc open) | implemented as C1-3 reads it, plus the C4 rebinding and the C4-1 numbering |
| C2-1 | item 1 **next row (C6)**; items 2 and 3 **resolved here** (fixes 2 and 5) | adapters spec in C2-1 §1 |
| C2-2 | item 1 **owner/registrar** (projection formula); item 2 **resolved here** (fix 3) | |
| C2-3 | **owner/registrar** | confirm the §5 readings; unwired: SearchQA tail acceptance slice, ALFWorld selection path, SpreadsheetBench shortcut probe, LiveMath checker |
| C3-1 | **owner** | canaries exist for SearchQA and ALFWorld only; OfficeQA, LiveMath, SpreadsheetBench need a decision (a/b/c) |
| C3-2 | item 1 **next row** (`write_supply`/`apply_exclusion` must require the persisted exclusion record); item 2 **resolved here** (fix 4) | |
| C4-1 | **resolved here** (fix 1) | |
| C5-1 | **next row, before chains G and D run together** | no unit drain is wired: `drain_check` and `drain_unit` have no caller in the package, and no worker gets `tag=` |
| C5-2 | **next row** | pre-check containers still `continual-eval-<uuid>` with one `rm` try; S2 `leftovers` row lists `execskill-sbx-` only |
| C5-3 | **owner/registrar** (v1.1 note) | J5 re-derivation, probe deal, SearchQA carrier reading, names, "3 tries, 10 s", restart-once, residuals |
| C5-4 | **next row** | `Worker.restarts` and `Worker.cleanups` are not copied into shell or cell records |
| C5-5 | docstring **resolved here** (fix 5); `rounds.balance` **owner/registrar** | `rounds.balance` has no caller |
| fixer-1 | **owner/registrar** (v1.1 note); the `seal-addendum` CLI subcommand **next row** | it needs the run root and evidence from the manifest, like the other A13-1 adapters |
| fixer-2 | **owner** | "short-answer share" has no registered definition |
| fixer-3 | resolved: registrar decision 2026-10-22, implemented by C5 (one guess per SearchQA reply) | the reading is C5-3 item 3 |
| fixer-4 | resolved on the CLI side (C3: `exclude-tests`, `make-manifest` writes `shared/test-canaries.json`) | the other three benches are C3-1 |
| fixer-5 | resolved: one ledger per chain (registrar decision, C2); the CLI follow-up resolved here (fix 2) | |
| fixer-6 | items 1-4 and 6 used by `step.py` and the e2e (C2, C4); items 5 and 7 **next row** | the adapter must fill `Setting.branch`/`longest` from the verified manifest and assert the safety-6 invariants |
| fixer-7 | main-agent part **resolved here**; owner part **owner** | no sealed manifest, smoke spec or S0 record exists on dl: `/data/execskill-20261021-pre` holds only `smoke/shared/exclusion-consent.json`, and the old hash `d19cbe49…` appears only in notes A3, B2, fixer and the ticket itself. The owner still has to confirm that the change stays in v1 |
| fixer-8 | resolved (C3: `exclude-tests`, persisted records, manifest binding, S0 row) | item 3's supply requirement is C3-2 item 1 |
| fixer-9 | client side resolved (C5: tags, bounded removal retries, worker isolation, loss classification, start retry) | rest: C5-1, C5-2, C5-4, and the S0 measurements |

Count: 42 tickets.
- **Closed (19)**: nothing is left, or what is left continues under another named ticket: A2-1, A4-1, A5-2, A6-1,
  A6-2, A7-1, A7-2, A9-1, A9-2, A10-2, A10-3, A11-1, A12-2, C4-1, fixer-3, fixer-4, fixer-5, fixer-8, fixer-9.
- **Partly closed (9)**: A9-3, A12-1, A13-1, C2-1, C2-2, C3-2, C5-5, fixer-6, fixer-7.
- **Open (14)**: A3-1, A5-1, A10-1, C1-1, C1-2, C1-3, C2-3, C3-1, C5-1, C5-2, C5-3, C5-4, fixer-1, fixer-2.

This integration closed C4-1 and the CLI remainder of fixer-5, and closed parts of C2-1, C2-2, C3-2, C5-5 and
fixer-7. No ticket file was edited; this table is the status.

## What must happen before launch (carried forward)

Next build row (C6) or main agent, in this order:
1. The A13-1 adapters (spec in C2-1 §1): `setting_of`, `services_of`, `chain.run`/`terminate` from the manifest,
   `evaluation.run_unit_spec` (arms F, C, P_F, T_F), `readout.report`, and a `seal-addendum` subcommand (fixer-1).
   They must fill `Setting.branch`/`longest` from the verified manifest (fixer-6 item 5).
2. C5-1: pass `tag=client.unit_tag(chain, unit)` to every unit's workers (`units.cell_context`, `router.plan`,
   replay, detectors, the engineer's C5 check, the step's factories) and call `client.drain_unit` when a unit's
   workers have exited. Until then no unit-level drain runs at all.
3. C5-2 (pre-check containers) and C5-4 (restarts and cleanups in the records), so S2 can report them.
4. C3-2 item 1 (the supply must require the persisted SearchQA exclusion record).
5. Gate (iii) again in a real `git clone` after the commit.

Owner or registrar decisions (no code can close these): A3-1, A5-1, A9-3 (MDE), A10-1, C1-1, C1-2, C1-3, C2-2
item 1, C2-3, C3-1, C5-3, C5-5 (`rounds.balance`), fixer-1 (v1.1 note), fixer-2, fixer-7 (owner part), and B5's
question whether the test-read twin seed should drop the chain.

## Files changed by this integration

- `skillopt/execskill/examiner.py`: `Generated.next_number`; `build(start=...)`.
- `skillopt/execskill/step.py`: `_build(start)`, `_generate` numbering and `numbered`, `_g_acc` start.
- `skillopt/execskill/chain.py`: `cap_check` re-check records; `RECORD_HASH` import.
- `skillopt/execskill/exclusion.py`: `release_path` (public).
- `skillopt/execskill/generators/sheet.py`: `apply` removes a dropped item's folder; the body moved into `_made`;
  `import shutil`.
- `skillopt/execskill/protocol.py`: `LEDGER` comment only.
- `skillopt/execskill/rounds.py`: module docstring only.
- `scripts/run_execskill.py`: `resume-ledger --chain`, `monitor` ledgers, `budgets` import, `release_path`, usage
  text.
- `tests/test_execskill_cli.py`: one new test, the parse test's `--chain G`, `release_path`, two imports.
- `tests/test_execskill_chain.py`: one new test.
- `tests/test_execskill_examiner.py`: T-EXAM-4's G_acc build and one assertion.
- `tests/test_execskill_e2e.py`: one assertion block in the acceptance test.
- `tests/test_execskill_generators.py`: one new test.
- This note.
