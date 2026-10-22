# Fixer notes: isolation, safety and statistics reviews (route B, `fivebench-execskill-v1`)

Written by the fixer, 2026-10-22. Inputs: `review-isolation.md` (3 BLOCKER + 9 MAJOR), `review-safety.md` (6 MAJOR) and
`review-statistics.md` (1 BLOCKER + 7 MAJOR).

## How the work was done

- No paid model calls; no test-pool data was read; no git command that changes state was run. The fixtures are
  synthetic, and the tests use fakes.
- No frozen file was edited (`skillopt/coevo5`, `skillopt/continual_eval`, `scripts/run_coevo5.py`,
  `scripts/weak_solver_probe.py`, the scorers). `git status` on dl shows no change under those paths.
- Exceptions come only from `skillopt.coevo5.outcomes`, or are the existing `cells.Pause` and `require` ValueErrors;
  no exception class is redefined. New records carry `fivebench-execskill-v1-<kind>` and `evidence`, and are written
  once with `write_json`.
- Each fixed finding has a regression test named after it (`test_isolation_<n>_*`, `test_safety_<n>_*`,
  `test_statistics_<n>_*`). No test was weakened. Where a fix changed behaviour that an old test pinned, that test now
  pins the stricter behaviour (see "Existing tests that changed").
- Suite on dl (the command from the task): **918 passed, 0 failed in 136.56 s** (896 baseline + 22 regression tests). The baseline before the fixes was 896 passed.

## Findings

Status: **fixed**; **partial** (the code part is fixed, and the rest is in the named ticket); **deferred** (the reason
and the ticket are given).

### Isolation review

| # | Sev. | Status | What was done | Regression test | Ticket |
|---|---|---|---|---|---|
| 1 | BLOCKER | deferred | `step.py`, `examiner.py`, the `run_unit_spec` / `report` adapters and the e2e test do not exist yet (A12-2, A13-1). This is the main build, not a fix. The modules they will call now check provenance themselves (findings 5, 6, 8, 9). **Do not launch the pilot until this exists and passes.** | - | fixer-6, A12-2, A13-1 |
| 2 | BLOCKER | fixed | An ALFWorld test game's routing view (`ALFWORLD_ROUTING_VIEW`) is made in memory inside the unit, from one reset under the episode pool (`evaluation.alfworld_reset`, `_with_views`), and is never stored. `test_plan` refuses a public record that already carries a view. Each cell carries its room. | `test_isolation_2_an_alfworld_test_game_is_routed_on_a_view_made_in_memory` | fixer-1 |
| 3 | BLOCKER | fixed | `EvaluationStore.scorer_dir` = `<attempt>/transient/host_only/scorer_artifacts/<position>`. This passes the frozen v7 `host_only` guard and is deleted by `finish()`, which records the deleted files (`_delete_tree`: count and manifest sha256). | `test_isolation_3_the_scorer_directory_passes_the_frozen_v7_guard_and_is_deleted` | fixer-1 |
| 4 | MAJOR | partial | `exclusion.alfworld_test_identity` now stops on any test/supply game overlap, naming only the count (§10 S0: pass, otherwise stop). The `exclude-tests` CLI, the persisted records, the manifest binding and the S0 row are still missing. | `test_isolation_4_an_overlapping_supply_stops_with_counts_only` | fixer-8 |
| 5 | MAJOR | fixed | `engineer.Context` refuses: a trajectory that is not a verified run unit (`<chain>/s<k>-<bench>/run`) of the label's chain and bench at step <= k; references on ALFWorld, or for items that did not fail (answer-shape checked); detector input other than `detectors.counts`; a `previous` outside the decision/faults/format schema. | `test_isolation_5_the_engineer_context_refuses_inputs_of_the_wrong_provenance` | fixer-6 |
| 6 | MAJOR | fixed | New `detectors.examiner_diagnosis(halves, bench=)`: write half only (it refuses hold-half cells and unsplit input), on `masked_view(purpose="examiner")` with the mechanical mask. `diagnosis` is engineer-only. `counts()` is the engineer's detector input. | `test_isolation_6_the_examiner_diagnosis_reads_the_write_half_on_masked_views` | fixer-6 |
| 7 | MAJOR | fixed | `trajectories.mask_answers` also masks restatements of the carried answer: word-bounded, case-insensitive, whitespace-flexible, numbers matched by value. On LiveMath it masks the option letter references and the chosen option's text (`choices`). | `test_isolation_7_a_restated_answer_is_masked_with_the_carrier` | - |
| 8 | MAJOR | fixed | `research._send` screens every string the researcher sees: texts, question, rule, subject names and parameter names. `parameter_choice` bounds names to 1..6, each non-blank and at most 40 characters. | `test_isolation_8_every_string_the_researcher_sees_is_screened_and_names_are_bounded` | - |
| 9 | MAJOR | fixed | `Worker.start` requires the inputs directory to hold exactly one regular, non-symlink `input.xlsx`. The policy also bans `ExcelFile`, `ExcelWriter` and `HDFStore`. **The policy sha256 changed** (see below). | `test_isolation_9_the_input_mount_holds_exactly_input_xlsx`, `test_isolation_9_file_reading_constructors_are_banned` | fixer-7 |
| 10 | MAJOR | partial | `unit_scan` covers the unit root, `shared/host_only/diagnostics` (diagnostics and child logs) and `shared/test`. It runs before the first call of an attempt and on every exit, pause and exception included, and before the infrastructure pause. The test-side SB qualification deletes its `host_only` scorer artifacts (`scorer-artifacts-deleted.json`). Still open: no code creates `shared/test-canaries.json`. | `test_isolation_10_the_scan_covers_the_diagnostics_and_shared_test_and_runs_before_any_call` | fixer-4, fixer-1 |
| 11 | MAJOR | fixed | Before a new attempt, `_leftovers` deletes every earlier attempt's leftover transient store, writes `transient-deleted.json`, and lists the cleaned attempts in `canary_scan.json`; the scan covers the old attempts. Pause and exception paths write the deletion record (`_closed`). | `test_isolation_11_a_crashed_attempts_transient_store_is_deleted_with_a_record`, `test_isolation_11_a_pause_deletes_the_store_with_its_record_and_scans` | fixer-1 |
| 12 | MAJOR | fixed | `evaluation.seal_addendum` hashes `shared/formal-addendum.md` and writes the write-once record `formal-addendum` {document, sha256, written_at = this code's clock}. `_addendum` re-hashes the document against the seal and refuses a self-declared JSON. `unseal` runs only once every chain directory of the root has ended. | `test_isolation_12_a_self_declared_or_changed_addendum_is_refused_and_sealed_once`, `test_isolation_12_no_unseal_while_another_chain_of_the_root_is_running` | fixer-1 |

### Safety review

| # | Sev. | Status | What was done | Regression test | Ticket |
|---|---|---|---|---|---|
| 1 | MAJOR | deferred | One ledger halts both chains. Both remedies change registered behaviour: per-chain ledger roots split the single `overall` cap; one ledger needs REG text and recovery steps. Owner / registrar decision. | - | fixer-5 |
| 2 | MAJOR | partial | The solver block records `longest`. `manifest.check_clients` re-derives the whole block, B included, from its `branch` / `longest` (`solver_block`), so B = M on branch E, or branch N without `longest`, is refused. Still open: the adapter must fill `Setting.branch` / `longest` from the verified manifest (it does not exist yet), and the S1-b record hash is not yet bound. | `test_safety_2_the_ledger_bound_equals_the_registered_derivation` | fixer-6 |
| 3 | MAJOR | deferred | Container tags, the drain's wiring and a bounded rm retry need the A5-2 decision and the unit runner (absent). Out of time. | - | fixer-9, A5-2 |
| 4 | MAJOR | deferred | Worker non-dumpable, per-call process groups, and a refusal on `call` mapped to `_Lost`: these are `worker.py` / `client.py` changes plus S0 probe rows. Out of time. | - | fixer-9 |
| 5 | MAJOR | deferred | `docker inspect` classification of `_Lost`, a start retry, and limits measured under load in S0. Out of time; the limits need an S0 measurement. | - | fixer-9 |
| 6 | MAJOR (unverifiable) | deferred | The invariants depend on the absent step and adapters. They are listed as asserts for that code. | - | fixer-6, A12-2, A13-1 |

### Statistics review

| # | Sev. | Status | What was done | Regression test | Ticket |
|---|---|---|---|---|---|
| 1 | BLOCKER | fixed | The readout is cell-aware. F, P_F and T_F cells that share C's cell (`shared_with`) read C's outcome, and a contrast of two arms that read the same cell contributes exactly 0: a shared cell is never scored on L and H at once. The §6.3 `shared_unanswered` mask (every arm unknown, nothing delivered) is removed from every contrast and reported. | `test_statistics_1_a_shared_cell_is_one_outcome_never_scored_on_both_sides`, `test_statistics_1_the_shared_unanswered_mask_leaves_every_contrast` | - |
| 2 | MAJOR | fixed | J6 tests every registered byte-identical pair: C-S when the card is the parent, and S_dup-S. Each pair has its own p, and J6 passes only if all pairs pass. | `test_statistics_2_j6_tests_every_byte_identical_pair` | - |
| 3 | MAJOR | fixed | `acceptance.dispatch(..., clock=, sleep=)` waits out `BLOCK_GAP_SECONDS` (OfficeQA 2 h) before every later block. J5 checks the realized gap (`block_gap`: windows, gaps, required, ok). | `test_statistics_3_officeqa_blocks_keep_the_registered_gap` | - |
| 4 | MAJOR | fixed (module) | `acceptance.settle`: "undetermined" raises `Pause("acceptance_undetermined")`, so the batch is consumed but undecided (§13). Only accept or reject marks items decided. J5 carries `pause`. The step driver that must call `settle` is absent. | `test_statistics_4_an_undetermined_round_pauses_and_stays_consumed_but_undecided` | fixer-6 |
| 5 | MAJOR | partial | §8.3 `arm_table`: v2, official, official-completion and lenient shares; unknown counts; flags; format; fault cells and kinds; enable rate; time windows with answer-tag share and mean completion tokens. §8.1: F - P_F placebo contrast (descriptive). §6.2: the code-vs-text guard `cannot_act_by_construction`. `unseal` now carries the inputs: official, final, lenient, answered, room, carrier, fault kinds, worst delivery, timestamps, completion tokens. Still open: the "short-answer share" has no registered definition. | `test_statistics_5_the_arm_table_reports_next_to_every_accuracy` | fixer-2 |
| 6 | MAJOR | deferred | The SearchQA two-channel pass contradicts the registration's own two promises. Owner / registrar ruling (a) or (b); the code is unchanged. | - | fixer-3 |
| 7 | MAJOR | fixed | Rooms come from `supply.task_folder` and pass through `test_plan`, the cells, `unit.json` (`rooms`) and `unseal`. Every ALFWorld contrast uses the room-cluster paired t (df = rooms - blocks) and reports `rooms`. An ALFWorld cell without a room is refused. Still needed: the owner confirms that §8.2 uses this model. | `test_statistics_7_alfworld_contrasts_are_room_clustered` | fixer-1 |
| 8 | MAJOR | deferred | The unit-blocked dispatch order needs the owner's sign-off. A9-2 request 2 stays open, and the code is unchanged. | - | A9-2 |

## Existing tests that changed (no assertion weakened)

- `test_execskill_evaluation.py`:
  - the addendum fixtures write the document and seal it (`seal_addendum`) instead of a self-declared JSON;
  - the continuation-check file list includes `formal-addendum.md`;
  - the cell keys include `completion_tokens`.
- `test_execskill_integration_b5.py`: the addendum is sealed through `seal_addendum`, and `formal-addendum.json` is no
  longer an owner file exempt from the record check.
- `test_execskill_acceptance.py`:
  - T-ACC-7 injects `sleep`. Before, it would really sleep 7,200 s; now it asserts the one gap wait.
  - The fixtures keep the OfficeQA gap.
  - The J6 shape is now per pair.
- `test_execskill_integration_b3.py`: injected clock and sleep, `acceptance.settle`, the per-pair J6, and `block_gap`
  asserted.
- `test_execskill_engineer.py`, `test_execskill_replay.py` and `test_execskill_integration_b4.py`:
  - trajectories are run units (`D/s1-<bench>/run`);
  - references are given only for failures;
  - the detector input is `detectors.counts`.
- `test_execskill_exclusion.py`: the overlapping supply now expects the stop, not `disjoint: False`.
- `test_execskill_manifest.py`: the solver blocks carry `longest`.
- `test_execskill_mutations.py`: mutation 19 (the evaluation store keeps raw replies) targets the new sealed-call line.
  The mutation itself is unchanged and still makes its named test fail.

## Policy hash change (isolation 9)

`sandbox/policy.json` was regenerated with `policy.write_policy_json()` on dl:
`d19cbe494f0c098f583af6c7a40a8ccd1f0a17f6c026885643ae4d8f5132fc7d` -> `b21d2f0337f98eee814834a67de7965f0af6489104ea3b7a746cc07686a8c926`.
The worker reads the host's `policy.py` through the read-only `/runner` mount, so no image rebuild is needed. Notes A3
and B2 quote the old hash as history. Confirming that no sealed manifest pins the old hash is fixer-7.

## Files changed

- Code (`skillopt/execskill/`): `evaluation.py`, `protocol.py` (`FORMAL_ADDENDUM_DOCUMENT`), `readout.py`, `acceptance.py`,
  `trajectories.py`, `research.py`, `engineer.py`, `detectors.py`, `sandbox/client.py`, `policy.py`, `sandbox/policy.json`,
  `manifest.py`, `exclusion.py`.
- Tests (`tests/`): `test_execskill_{evaluation,readout,acceptance,integration_b3,integration_b4,integration_b5,replay,engineer,
  research,trajectories,policy,sandbox,detectors,manifest,exclusion,mutations}.py`.
- Tickets: `tickets/fixer-1.md` ... `tickets/fixer-9.md`.

## What is missing (for the gate)

- The two remaining BLOCKER-class gaps are isolation 1 and safety 6. `step.py`, `examiner.py`, the adapters and the e2e
  test do not exist, so no isolation claim has been exercised end to end. Fixer-6 lists the contracts that code must use.
- Owner / registrar decisions: fixer-1 (v1.1 note), fixer-2 (short answer), fixer-3 (SearchQA), fixer-5 (ledger scope),
  fixer-7 (policy hash), A9-2 (dispatch order), A5-2 (drain tags).
- Code not written for lack of time: fixer-4 (canary creator), fixer-8 (exclusion CLI and S0 row), fixer-9 (sandbox
  lifecycle and fault attribution).
