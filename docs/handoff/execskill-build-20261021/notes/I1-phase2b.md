# I1 phase 2b (integrator, route B): 14:4x items, P2C follow-ups, registrar 15:0x-15:5x and the R7 decision

Agent I1, 2026-10-22, 14:3x-17:4x (dl clock). Protocol fivebench-execskill-v1. Build tree `/data/execskill-dev`
(= the Mac mount `/Users/dulin/remote/dl`). **Zero model calls, no network, no docker, no git write.** No test pool
read, nothing written under `/data/coevo5-*`, `/data/execskill-20261021-pre`, `/data/execskill-history`,
`/data/execskill-20261021-pilot` (the owner's consent lives there) or any real run root; frozen code
(`skillopt/coevo5/`, `skillopt/continual_eval/`, frozen `scripts/`) untouched. Throwaway copies and pytest roots
`/tmp/i1-*` on dl were deleted. Progress log: `notes/I1-progress.md`.

## Status

| Part / item | State |
|---|---|
| (a) 14:4x: `smoke.LEAKAGE_CALLS`/`DESCRIBER_CALLS`, GLM floor max(measured, `ROLE_INPUT_BYTES`), I1-2 applied, acceptance on `readout.windows`/`evaluation.completion_tokens`, row 12 test manifests | done 14:57 (progress log) |
| (b) brief report: P2C not finished | sent |
| (c) 15:0x: manual `smoke --stage` path S0/S1 only; `probe --fake`; confirmation reservation runbook line | done, tested, mutation entries 60-63 |
| (c) 15:1x: owner consent already written: pilot-runbook §2 go check and §7.1 | done |
| (c) 15:3x ticket P2C-1: `step-unit` needs a passed `confirm.json` of the same run and chain | done, tested, entries 56-57 |
| (c) 15:3x ticket P2C-2: the read gate prices the read units still to run (per-bench terms, chain G's factor, ceiling) | done, tested, entries 58-59 (48 moved to `part`) |
| (c) 15:5x R1, R2, R3, R4, R5, R6 (a), (b), (d), (e) | each confirmed in the code first, fixed, one test each |
| (c) 15:5x R6 (c) | not applied as worded: ticket I1-3 |
| (c) R7 decision 16:1x: R7a, R7b, R7c | applied, tested, entries 74-77 |
| (c) mutation entries | 56-77 added (22); entry 48's site moved |
| (c) CLI fake rehearsal S0 → S1 (`probe --fake`) → S2 ∥ S3 → S-E6 → summary → `test-read-estimate` | done: one test, two `smoke-run` processes side by side |
| (c) re-pin code maps (PR-C12-2 item 3) | nothing to re-pin (see below) |
| (c) fresh-copy whole suite, gate (iii), all mutation entries | see Tests |
| (c) runbooks | pilot-runbook and smoke-runbook updated |

## Registrar 15:0x, 15:1x, 15:3x (line numbers as of 17:00)

- `scripts/run_execskill.py`: `MANUAL_STAGES = ("S0", "S1")` (:127); `smoke_stage` (:365) refuses any other stage
  ("smoke --stage records S0 or S1 only ...") and argparse limits `--stage` to S0/S1. `probe --fake` (:337): refuses
  `--env-path` ("probe --fake names no credential"), calls `smoke.rehearsal_roots(spec, probe=True)`, requires the
  spec's probe root, and runs `smoke.run_probe` on `tests/execskill_fakes.ProbeGateway` behind the real client with a
  throwaway fake credential file and slot pool under the probe root, `evidence=smoke.REHEARSAL_EVIDENCE`.
  `smoke-make --probe-root` (default `protocol.PROBE_ROOT`) gives a rehearsal its own probe root.
- `skillopt/execskill/smoke.py`: `REHEARSAL_EVIDENCE = "engineering_fixture"` (:120); `record(..., evidence=)`;
  `_evidence_of` (:241) labels the summary a rehearsal's when any recorded stage is; `rehearsal_roots` (:249) refuses
  the registered smoke root (and, for the probe, the registered probe root); `run_stage(fake=True)` calls it and labels
  S2/S3/S-E6 records as a rehearsal's (`smoke_roles` S3 too); `run_probe` now also requires the spec's probe root
  (S2 reads the probe's receipts there).
- `skillopt/execskill/chain.py`: `confirmation(root, run, chain)` (:202), used by `first_call`'s relaunch reuse and by
  `step.run_unit_spec` (:1137, before anything is touched; ticket P2C-1). `step-unit` also declares
  `budgets.first_call_caps(chain)` beside `chain_caps` (its ledger then equals `chain.run`'s). `read_estimate_record`
  (:289) writes the per-bench `terms` (`protocol.read_estimate_terms`, :547 of protocol.py) and labels a rehearsal
  smoke's estimate by the result's evidence. `read_budget` (:347): `part` = the estimate on a first start, else
  ⌈Σ terms of the read units without `unit.json`⌉; chain G's `used` = ⌈part × max(1, factor_G)⌉; `need` = ⌈1.3 ×
  used⌉; the gate records `units` and `part` (ticket P2C-2).
- `skillopt/execskill/manifest.py`: `setting_of` copies `data.test_read_terms[chain]` into `extra` and refuses terms
  that are missing, incomplete, not positive or of another estimate (`_read_terms`, :470).

## Registrar 15:5x, R1-R6 (verified in the code before any change)

- R1 confirmed (`_references` forwarded only `answer`/`answers`, absent on SpreadsheetBench). `step._sheet_reference`
  (:657) reads the failed run item's first answer workbook as the frozen scorer reads a reference
  (`spreadsheet_compat`: cached values, `resolve_targets`, `_iter_cell_names`, an explicit empty formula string is
  ""), giving {"<sheet>!<cell>": value} (`_scalar`, :645), the table shape `engineer._answer_shape` takes; None on an
  unavailable formula cache, an unresolved target or an unreadable file. Leakage corpus unchanged.
- R2 confirmed (`_inputs_dirs` mounted only the current SpreadsheetBench step's items). `_inputs_dirs` (:733) mounts
  every stored SpreadsheetBench trajectory's own public workbook whatever the step's bench (publics by item key
  `rounds.key`, as a trajectory's `task_id` is: the bench's pool, plus this step's run slice on SpreadsheetBench); an
  unknown item is refused (the old code skipped it silently, which is how a replay lost its /input). The engineer
  unit passes all stored trajectories. My first version keyed the publics by the bare item id, and its unit test used
  bare ids too; the fresh-copy e2e caught it (both chains paused at `s1-spreadsheetbench/engineer`, "A stored
  SpreadsheetBench trajectory of a known item"). Fixed, and the unit test now uses item keys.
- R3 confirmed (solver.py rendered bindings and the compute invitation on SpreadsheetBench). `solver.Shell.before`
  skips the `bindings` hook outside QA (:373). Static refusal at the minimal place, engineer C1
  (`engineer._structure`): a `bindings` hook whose `excluded_benches` does not list spreadsheetbench and alfworld fails
  C1 with `bindings_is_qa_only: list spreadsheetbench and alfworld in excluded_benches` (`BINDINGS_SCOPE`, :75).
  `replay.py`/`donors.py` were not changed: a learned procedure cannot reach them with such a scope (C1), and the
  fixture package's `fx-bindings` has origin officeqa.
- R4 confirmed. `examiner.policy_payload` states `request_kinds` per bench (`request_kinds`, :324: ALFWorld
  `selection_hint`; else `family_material`, plus `parameter_choice` when a family has a choosable parameter) and per
  family `parameter_choice_names` (`choosable`, :319; kinds `CHOOSABLE_KINDS` = int, ints; none on SpreadsheetBench).
  Validation and the void-on-invalid fallback unchanged.
- R5 confirmed (no pilot role log). Each step unit attempt appends its role calls once to `<unit>/role-calls.jsonl`
  (`step.role_calls`, :295; `ROLE_CALLS`, :130): {attempt, role, label, request_sha256, valid, reason, reply, and
  `adjudicator_reason` for `leak_adjudicate`}, whatever the attempt's end; no receipt, consent or ledger figure.
- R6 (a) confirmed: `compute` reads − × ÷ as - * / (`SIGNS`, :55); a doubled multiplication sign is a syntax error,
  never a power (`POWER_OF_SIGNS`, :56); literals keep their source text.
- R6 (b) confirmed: the band and shortcut gates count `judge.v2.token` (`examiner._probed`, :705); a cell stopped
  before its verdict counts as unknown.
- R6 (c) not applied: ticket I1-3. A refusal keyed on the pause record would strand interrupted attempts (the units
  rule needs `recovery.json` after an interruption too); the hazard is a `recovery.json` written into a running
  attempt. Options and a recommendation are in the ticket; pilot-runbook §6.3 now says to run `recover` only while
  the chain is idle.
- R6 (d) confirmed: `make-manifest` without `--s0-pins` refuses with "give --s0-pins" before anything is written; pins
  without root, data or evidence are refused too.
- R6 (e) confirmed: `step.cost_projection(..., attempt=)` takes the run scope of the attempt that completed the unit,
  and `_run` passes that attempt (from `unit.json`).

## R7 decision 16:1x

- R7a: `engineer.Context.spent` (validated 0..`ENGINEER_CALLS`); `_ask` stops at `spent + calls >= ENGINEER_CALLS`;
  the sealed record adds `earlier_calls`. `step._engineer`: `engineer` starts at 0, `engineer-2` at the completed
  first unit's `calls` (:764); a redo attempt restarts its own count.
- R7b: `protocol.ROLE_CAPS` = engineer 2.5M, examiner 3.0M, examiner:research 4.6M (10.1M per step, 20.2M for two);
  `<c>:glm` 30M and overall 210M unchanged; budgets.py docstring, pilot-runbook §3.5 cap table.
- R7c: `smoke.LEAKAGE_CALLS` = 2 × 3 first checks + min(6 − 2, 6) checks after fixes = 10 (the coded per-step maximum
  after R7a; `ENGINEER_UNITS` = `SELFTEST_PASSES`); the engineer row's next reservation is floored at
  `ENGINEER_REQUEST_FLOOR` = 220,000 + 5,170 (the engineer system prompt) = 225,170 bytes, i.e. 968,264 tokens
  (other rows stay at 947,584). smoke-runbook §6.2 updated.

## Mutation entries 56-77

56-57 P2C-1 (the `confirmation` call; its identity check), 58 P2C-2 relaunch pricing, 59 the manifest's terms check,
60 the manual stage refusal, 61 `probe --fake` credential refusal, 62 its registered-probe-root refusal, 63
`run_probe`'s probe-root check, 64-65 R1 (the reference call; uncached formula as unavailable), 66 R2 (the pool's
publics), 67-68 R3 (shell skip; C1 refusal), 69 R5 (the unit's log call), 70 R6 (a), 71 R6 (b), 72 R6 (d), 73 R6
(e), 74-76 R7a (engineer-2's start count; the engineer's step-wide stop; the Context range), 77 R7c (the engineer
floor). Entry 48 now mutates the `part` line. No entry for R4 (payload content, no check to remove) or for `_run`'s
attempt argument (no test drives a chain-G redo through `_run`; `cost_projection` is tested directly).

## CLI rehearsal

`tests/test_execskill_cli.py::test_cli_rehearsal_runs_the_trimmed_smoke_end_to_end_as_an_engineering_fixture`:
synthetic exclusion unit (`exclude-tests` on synthetic panels), `smoke-make --probe-root`, `smoke --stage S0`,
`probe --fake` (41 scripted sends, branch E), a smoke manifest after S1, `smoke-run --fake --stage S2` and `--stage
S3` as two subprocesses side by side, `smoke-run --stage SE6 --fake`, `smoke-summary` (passed), `test-read-estimate`
on the rehearsal root. S1-S-E6, the result and the estimate are `engineering_fixture`; S0 (manual path) keeps
`smoke`. S2 judged the rehearsal probe's S1-e control receipt (`s1e_mismatch` = [True]). 52 s on dl.

## Code maps

No test pins a code map: the manifests' code maps (`manifest.pin_code`) are computed when a manifest is made and
verified against the running tree, so PR-C12-2 item 3 leaves nothing to re-pin in the tests. The only static pins are
`LEXICON_SHA256` (notes lexicon) and `CALC_SHA256` (the registration's calc file); neither file changed. The dynamic
checks pass on the fresh copies. The snapshot's source list (`verify-snapshot`, `$PRE/source-sha256.txt`) is the main
agent's, after the commit.

## Tests (dl, zero calls, zero network)

All runs on fresh copies (`cp -a skillopt scripts tests pyproject.toml`, no `__pycache__`) unless noted.

| Run | Result |
|---|---|
| Targeted, live tree, after R1-R6: compute, examiner, shortcut_sb, solver, engineer, step cost projection, cli manifest | 119 passed |
| Targeted, live tree: step, examiner, engineer, compute | 95 passed (136 s) |
| Targeted, live tree, after R7: engineer, smoke, protocol, step blocked/no_change | 69 passed |
| Mutations 48 and 56-77 (`-k`; the fixture first ran all 78 entries' named tests unmutated) | 23 passed (125 s) |
| cli, smoke, smoke_rehearsal, smoke_roles (with the new CLI rehearsal) | 77 passed (178 s); the CLI rehearsal alone 52 s |
| Whole suite, first try: the 55 `tests/test_execskill_*.py` modules except mutations, plus `test_coevo5_core.py` and `test_weak_solver_probe.py` | 1221 passed, 11 errors (every e2e test: the R2 key bug above) |
| `--help` on every subcommand of the real script (cwd `/tmp`) | 35/35 exit 0 with `usage:` |
| Mutation suite, before the R2 fix | 78 passed (191 s) |
| **Whole suite after the R2 fix** (gate (iii): e2e included) | **1232 passed** (1036 s, beside the mutation run); no bytecode written |
| **Mutation suite after the R2 fix** (gate (iii); 78 entries, each fails its named test) | **78 passed** (216 s) |

`smoke-make --dry-run` with fakes is `test_smoke_make_dry_run_writes_nothing_and_cleans_the_environment` (in the
suite). `ruff --select F` on the changed files: no unused import or undefined name (only pytest-fixture
redefinitions and one pre-existing loop-variable shadowing in `test_execskill_cli.py`).

## Flags for the coordinator and registrar

1. Rehearsal labels: S0 recorded by the manual path keeps the `smoke` label inside a rehearsal root (the path cannot
   tell a rehearsal); the result, and so any estimate made from it, is labelled `engineering_fixture` by its other
   stages, and pilot-runbook §3.3 asserts `evidence == 'smoke'`.
2. Added beyond the letter of 15:0x: `run_probe` requires the spec's probe root; `smoke-run --fake` refuses the
   registered smoke root (`rehearsal_roots`); `step-unit` declares `first_call_caps`.
3. `docs/handoff/execskill-pipeline-explained-20261022.md` was not updated for R1-R7 (not mine).
4. Pre-existing lines over 120 characters remain in `tests/test_execskill_protocol.py` (the moved-constants test),
   `tests/test_execskill_mutations.py` (entries 03, 09, 13), smoke.py :292, run_execskill.py :222.
5. Remaining ticket: I1-3 (R6 (c)). The formal-chain gaps of 15:5x are not pilot items.
