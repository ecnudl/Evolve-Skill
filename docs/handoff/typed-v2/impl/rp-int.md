# Step rp-int: read plan integration (pass, chain, prepare, smoke, CLI)

Implementer report (step id rp-int, batch 3). 2026-11-12. Sources: addendum D9-D17, RP1-RP13 (RP13 binding: constants
re-exported from `T/__init__.py`; the pass mounts every item with exactly the frozen library and type map it records);
spec/read-plan.md (all of 1.A-1.D, 2, 3, 4, 5, 6); spec/schedule-lock.md Part A; impl/6s.md; impl/rp-core.md.
`T/` = `skillopt/execskill/typed/`, `C` = `T/chain.py`. Starting point: commit de7346c plus the finished step 6s in the
working tree (no earlier attempt of rp-int). Not mine: `T/readout.py`, `tests/test_typed_readout.py` (agent rp-ro).

## Plan

- [x] Read: spec/read-plan.md in full, addendum RP1-RP15, impl/6s.md, T/readplan.py core + its tests, rp-core reports.
- [x] `T/__init__.py`: re-export READ_PLANS, READ_PLAN_DEFAULT, IDENTITY_VERSION, record versions, pause reasons (RP13).
- [x] `T/prepare.py`: `read_plan` (R2, R3), smoke-only `read_plan_probe` (R7, Q20), pair checks, `load_manifest`.
- [x] `T/readplan.py` (extend, do not rewrite the core): capture selector and capture call through the injected
      `solve_fn` and real `mount.mount` (R17, R19); sealed inputs (R78); the pass (R16-R34) mounting with the recorded
      frozen objects (RP13); plan restore (R44 c); replay core (R47); post-read check (R41); fallback / reasons.
- [x] `C`: state keys (R5), solver settings record (R75), `plan()`, replay child (R76), `--stop-after-plan` (R77),
      `read_classes` with both sweeps (R35-R39, R42), `reads(event, benches)`, R44 verification and recovery,
      R46 completeness, RP10, RP11 with Q24 option A.
- [x] `T/smoke.py`: smoke manifest fields, `fake_solve` `public_hash`, the pass on the practice panels, the probe,
      `checkpoint` kill points (R92).
- [x] `scripts/run_typed.py`: `prepare --read-plan`, `--read-plan-probe`; `run` / `smoke --stop-after-plan`;
      `smoke --resume`; `plan-replay` (R47, R47b); `--fake-kill-at` (R92); read counts in `state_summary`.
- [x] Tests: `tests/test_typed_readplan.py` (T1-T6 both bases, T8-T12, T18, T19, T21-T23, T25, T26); economy loop
      in schedule/chain tests (T16, T17); `tests/test_typed_cli.py` (options, plan-replay, exit codes, T24, kill
      points as subprocesses).
- [x] Own test files green during the work; at the end the whole `tests/test_typed_*.py tests/test_typed2_*.py` once.
- [x] Final sections: Done, Tests, Choices, Disagreements, Left for later steps.

## Done

`T/readplan.py` (core untouched; an integration section appended): `READ_PLANS`, `READ_PLAN_DEFAULT`,
`READ_PLAN_SCHEDULES`, `READ_PLAN_PAUSES` (= `PAUSE_REASONS`), `SOLVER_SETTINGS_VERSION`, `CHECKPOINTS`,
`PLAN_PROBE_EVENT_BENCH`; `check_read_plan` (R2, R3, R7, Q20), `parse_probe`; `solver_settings_record` (3.5: eight
named keys per bench, refuses URL / path / credential-like / long text) and `solver_settings_of_block` (route-B solver
block or chain D's route-B pin to the 3.5 row); the pass `run_pass` (R16-R34, R78, R80, R92): `.part` removal,
`frozen_states(load)` (each step's state loaded once through the chain's verified loader; C0 and C share s0, RP13),
`stored_inputs`, `open_plan_panels` (the one panel path `reads.open_panel`, label `<chain>/test-read-plan`, heavy lock
for the sheet panel, live ALFWorld resets through `reads.preparation_reset` on a first pass, the stored views and no
environment on a re-run or replay), `plan_inputs` (two embedder batches; stored inputs re-checked, `view_mismatch`,
`inputs_mismatch`), then as the pass's own code every inputs file (checkpoint `after-first-inputs`), the identities via
`bench_entries` / `item_record_for` (`services.identity_fn` and `services.mount_fn` with `capture_selector`, both
handed the loaded frozen library and type map and `arm_of(event)`; `capture_first_request` through the injected
`solve_fn` with a `CaptureCall`, the real unit name, cell tag and an uncreated scorer path), `compute_files` ->
`plan_files`, identities files, `read-plan.json` last (checkpoint `after-plan-file`); `_records` maps a non-stop
exception to `identity_exception`, `propagates` lets `Paused`, `units.Stop`, route-B `Pause` and stop kinds through;
`_guarded` turns any other exception of the pass's own code into `ReadPlanError('pass_exception')` (Q24 A);
`recompute_files`, `replay` (R47: qualification pointer check `qualification_missing`, frozen changes and own
detections as `different` with a fixed code, information count `reembedded`), `stored_bytes`, `registry_hashes`,
`hash_seed` (R76), `check_representative` (R41 against the sealed identities file bound by the plan).

`T/__init__.py`: the ten read-plan names re-exported through a PEP 562 `__getattr__` (RP13). An eager import broke
`test_machinery_snapshot_binding_in_a_fresh_interpreter`: `readplan` imports `units`, which imports frozen machinery,
and the bare package must stay importable in the binding check.

`T/prepare.py`: `prepare(..., read_plan='full', read_plan_probe=None)` checked before anything is written; `read_plan`
sealed in every manifest, `read_plan_probe` in smoke manifests only; `read_plan_of`, `read_plan_probe_of`;
`load_manifest` calls `read_plan_of`.

`C`: Services fields `solver_settings`, `checkpoint`, `replay`; `_open_state(..., read_plan=)` (state block of 3.6 plus
`counts`; a resume with another mode is a hard error); `frozen_state(chain_dir, chain, k)` (the body of 6s's
`load_frozen`, which now calls it); `reads(event, benches=None)` (R37); runner methods `write_solver_settings` (R75,
before `confirm`, both read plans), `plan` (R20, R21, binding, `bound_here`), `pass_failed` (RP11), `void_plan`,
`unsettle`, `replay_plan` (R76, R44 c, d), `verify_read_plan` (R44 a-c), `recover_aliases` (R44 b for
`read_alias_invalid`), `bound_plan`, `alias_valid`, `settled`, `fresh_wanted`, `read_classes` (R35-R39, both sweeps),
`settle` (R39, ADV12 order), `void_bench` (R42, RP10), `fresh_complete` / `complete_reads` (R46, then `step-0..5`);
`run(..., stop_after_plan=False)` order under economy: settings, consent (learn_first run), confirm, freeze_anchor,
learn(1..5), verify, recover_aliases, plan, replay, optional `stopped_after_plan`, read_classes; module functions
`_read_plan`, `solver_settings_rows`, `replay_header`, `in_process_replay`, `replay_child` (fresh interpreter,
`--machinery-snapshot` when bound, exit / verdict mapping, `timeout`, `exit_<n>`), `worker_options_of`,
`replay_services` (no client, no credential file, no pool, no lock), `plan_replay` (the command's body);
`real_services` sets `solver_settings` and `replay`.

`T/smoke.py`: `CONFIGURED`; `synthetic_manifest(..., read_plan='full', read_plan_probe=None)`; `smoke_manifest(...,
configured=False)`; `run(..., configured, stop_after_plan, fake_kill_at)` (the CLI form's replay is the real child);
`fake_solve` rows carry `public_hash` (ADV8); `fake_checkpoint` (SIGKILL to the process group; 'replay-child' only in
the child), `fake_solver_settings`.

`scripts/run_typed.py`: `READ_PLANS`, `CHECKPOINTS` written out; `prepare --read-plan`, `--read-plan-probe E:B`;
`run` / `smoke --stop-after-plan`; `smoke --configured`, `--fake-kill-at` (fakes only); command `plan-replay --root
--chain [--smoke] [--fake] [--base-card] [--fake-kill-at]` with the R47b handler (exit 0 / 3, no traceback);
`read_counts` and `state_summary['read_plan']` (R73) for states with a read-plan block.

## Tests

Command: `mkdir -p /tmp/typed2-neutral && cd <repo-root> &&
TMPDIR=/tmp/typed2-neutral <python> -m pytest -q -p no:cacheprovider tests/test_typed_*.py
tests/test_typed2_*.py`. Last line: `680 passed in 68.11s (0:01:08)` (Python 3.13; no failure in rp-ro's files
`tests/test_typed_readout.py` at that moment). My files under Python 3.10 (`<python-env>`; no
3.11 exists on this Mac): `tests/test_typed_readplan.py tests/test_typed_cli.py tests/test_typed_readplan_core.py
tests/test_typed_schedule.py tests/test_typed2_shared.py`: `134 passed`.

New `tests/test_typed_readplan.py` (27 tests, real pass / mount / reads / replay on the fake services): T1 constants
and re-exports, prepare and load_manifest refusals, resume with another mode; the configured smoke end to end (each
class read once, aliases verified, S5 first and descending order, probe `smoke_probe` with lists equal to C's, R46 and
step markers); T18 (fresh cells' first request = the capture); T11 (no ledger unit `read-plan`, only the sealed files
and the plan); T23 grep of the open records and the read-plan parts of the state; T3 with empty frozen states under
both bases (9 fresh units); RP13 (every pass mount gets exactly the objects the frozen loader returned, step by step);
T19 (identity exception, capture failed, unstable second embedder run, post-read mismatch voiding a settled alias and
reading the bench fresh once each, pass failure twice -> void, 35 fresh); T21; T9 (edited plan restored, edited sealed
file -> void, deleted alias record re-settled with equal bytes); T10 / T26 (in-process replay equal, heavy lock never
entered, another base / inputs / frozen file -> different, real-root `qualification_missing`, the REAL child with seed
41 -> 42 equal, a base-'format' child different twice -> void, replay error twice -> void); T25; T17 (learn_first with
full: 35 fresh, no plan); T16 P5 (a stop inside S5's unit, resume sends no finished cell again); T12 (consent first,
registry, one qualification under the lock with the plan label, resets locked only under unit_shared, re-run without
live resets, replay without the lock). `tests/test_typed_cli.py` (+6): options and adapters, summary counts, T24 with
the real child (exit 5, hard error without recovery, no second stop) and `plan-replay` exits and printing, the three
kill points as subprocesses in their own session (exit -9, resume completes, no `.part`, classes and counts equal to
an uninterrupted smoke, every pair settled once, one send per fresh cell).

## Choices

- Pins moved on purpose (no test deleted or weakened): `tests/test_typed2_shared.py` 5w golden file list:
  `solver-settings.json` asserted present and taken out before the unchanged digest (R75 writes it under `full` too,
  T25); `minimal_manifest` in `tests/test_typed_reads.py`, the positive manifest in `tests/test_typed2_identity.py`
  and the prepared smoke manifest in `tests/test_typed2_base.py` gain `read_plan: 'full'` (R3 makes it required).
- The fake smoke's synthetic manifest keeps the code defaults (full reads), so every earlier fake-smoke test is
  unchanged (T17); the typed-v2 smoke values come with `smoke --fake --configured` (`smoke.CONFIGURED`). The flag must
  be given on the resume too (`smoke --fake --configured --resume`): the synthetic manifest is rebuilt at every start.
- `plan-replay --fake` always rebuilds the configured synthetic manifest (only it has an economy plan); `--base-card`
  on `plan-replay` exists so a test can build the mounts on another base (T10).
- The replay child of a prepared root uses `replay_services` (no clients, credential files, pools or locks) and gets
  M from `solver-settings.json` (R47); native is None for the capture (the sheet's first request holds no slot, R19,
  `X/solver.py` `_solve_sheet` checked).
- Plan header: `receipt_sha256` = the receipt's `record_sha256`; `manifest_record_sha256` = the manifest's record hash
  (a synthetic manifest: its canonical hash); `solver_settings_sha256` = the sha256 of the stored file's bytes, which
  is also the state binding.
- Failure codes: the pass's own detections and Q24's `pass_exception` go to `state['read_plan']['failures']`; replay
  outcomes too (`replay_different`, `replay_error:<code>`); a repeated entry voids (RP11, R44 d). Recovery outcomes
  use the core's names (`plan_restored`, `replay_equal`, `plan_void`, `alias_unsettled`, `paused_again`).
- Archived plan-owned files keep their directory with the suffix `.archived-<recovery n>` (no closed name, so never
  read as a record); voided alias records go to `read-alias/archived/<event>-<bench>-<n>.json` as specified.
- `state['read_plan']['counts']` (the plan's counts, hashes-and-counts only) added to the 3.6 block so that
  `state_summary` can print `fresh_planned` without reading the plan file.
- `stop_after_plan` under `full` is ignored (there is no plan); the summary adds `read_plan` only for a state that has
  the block, so the exact pin of `test_exit_codes_follow_the_chain_state` holds.
- T4-T6 are exercised through the scripted smoke (SpreadsheetBench `{C0} {C,S1,S2,S3}>S3 {S4,S5}>S5`, SearchQA, the
  probe) and the empty-state T3 under both bases, not as separate k = 1, 2, 3 and type-map-only fixtures.

## Disagreements

- 3.6 says a fresh pair's `state['reads']` entry has no `kind` ("fresh implied when absent"). The fresh entry is the
  read's mirror as typed-v1 stores it, and the mirror carries its own `kind: 'read-status'`; changing it would change
  `full` states (T17). Interface for rp-ro: `alias` and `void_alias` are the read-plan kinds, anything else is fresh.
- S2 (c) asks for byte-equal `read-plan.json` against an uninterrupted fake smoke. Two runs differ in the frozen
  receipts' and libraries' time stamps (schedule-lock S8; impl/6s.md), so the plan bytes cannot match. The kill test
  compares the class tables, counts, done units and sends, and the byte check is the resumed chain's own replay
  (`equal`).

## Left for later steps

- Step 7 (7g): `machinery.REQUIRED` from the AST scan now meets `skillopt.coevo5.cells.Pause`,
  `skillopt.execskill.errors.stop_kind`, `skillopt.validator_pilot.api.digest` (lazy imports in `T/readplan.py`) and
  `skillopt.execskill.profiles.cleanup_grace_seconds` / `ready_timeout_seconds` / `ZEBRA_PC_V15` /
  `LIVE_SANDBOX_UNIT_CAP` (`chain.worker_options_of`); the bound driver should run `plan-replay` once under
  `bind_machinery` (the child is started with `--machinery-snapshot` when the manifest is bound).
- rp-ro (readout): the resolver reads the alias / void entries above, `read-alias/*.json`, `read-alias/archived/`, the
  plan's classes, and must ignore `*.archived-<n>` files.
- Not built here: T2 against every item kind at integration level, T6 (a type-map-only change fixture), T8 at
  integration level (the core covers them), T9 (vi) a rebuilt mirror, P8 separately; the post-launch `replicate`
  command (RP1).
- Ops: the real pass's consent / registry / qualification path and live ALFWorld resets first run in the real run
  (K-H; T12 covers them with stubs). The fake smoke takes about 6 s; on dl the replay child imports the bound snapshot
  and reads the inputs files only.
