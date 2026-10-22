# I1 progress (integrator, route B, phase 1)

- 12:32 started: read C7b1, C7c, C6 (C6-3), tickets C7c-1/C7b1-1..3, registrar addendum C7b1-3, smoke-inputs.md (OPS1).
- 12:45 item 1 code (C7b1-3): qualify.engine_runtime/revalidate/same_engine_sources/snapshot_root; s0.sheet_row + collect(engine_qualification) with real-path precondition; CLI s0-collect --engine-qualification, sheet-runtime, make-manifest revalidation; tests qualify 3 new, s0 3 new, cli 3 new. Runbook step 2b pending (item 4).
- 12:45 item 2 code (C7b1-2/C6-3): supply.export_pool/write_pool_export/pool_pins/load_pool (+REGISTERED_POOLS, SHEET_QUALIFIED=91); CLI export-pools; s0.smoke_items reads the exported SearchQA file (load_pool + 600 check); tests supply 3 new, s0 1 new + 1 updated, cli 1 new.
- 12:45 item 3 done (C7c-1): smoke_run prints result.result.passed or the stopped report (exit chain.EXIT_PAUSED=3); smoke-recovery wired (smoke.add_arguments, HANDLERS, usage line); cli tests: 1 updated, 1 new.
- 12:50 item 2 real cross-check (zero calls, throwaway /tmp/i1-pools, deleted): export-pools from the v3 manifest EXIT 0; SearchQA 600 (400/200), sorted ids 901fb49e219da901, supply-order ids 332df1bffc67468e, items 120f123facc30534, smoke slice 280 = 198 train + 82 val (7033d48d685c4cba), run slice 300 (50ce48330655cf2d), all = OPS1; SB 120 -> 91 qualified (58 train/33 val) -> run 31 + accept 60; OQ 74 -> 24/50; LM 283 -> 119/100/64; ALF 57 (v3 pool; too few for the registered ALFWorld slices: the recommended pilot would need the fresh ALFWorld supply as its pool, ticket I1-1).
- 13:00 item 4 done (runbook merge): smoke-runbook.md rewritten (348 lines): OPS1's resolved inputs and sha256s (shell vars, $IN table, hfenv HFCLI, record hash acc5c07f not the file sha), step 2b (replay_sheet_v6 qualify from $SRC mirroring prep-v3f.sh:11, then sheet-runtime), export-pools + its expected digests, smoke-items on the export, s0-collect --engine-qualification, runtime pin builder, the S2 -> SN1 -> S4 (drill pause, exit 3) -> smoke-recovery -> S4 -> SE6 -> S3 (C7d) -> summary sequence, stale "not built"/"Python form until C7c-1" lines removed; open: S3 (C7d), control-cells/noise-anchor (registrar), C7c-2 (C7e), slot field deferred (safe failure), C7b1-1 documented, I1-1 (ALFWorld pool).
- 13:02 item 5 done: own files qualify+s0+supply+cli+runcli+manifest 94 passed, 0 failed (21 s); dependents canaries+engines+exclusion+fixtures+integration_b1/b2+registry+protocol+solver 111 passed (35 s); real script: all 34 subcommands answer --help (exit 0, "usage:"); no __pycache__ written; no /tmp/i1-* left on dl.
- 13:05 phase 1 done: notes/I1-phase1.md written; waiting for the phase-2 message (after C7d S3 and C7e one-block redo).
- 13:27 phase 2a started: read registrar addenda 13:0x, 13:2x, 13:4x, 13:5x, 14:1x.
- <=14:2x phase 2a: C7d-3 done (smoke-run --fake passes no default --env-path; test asserts the two refusals never reach run_stage)
- <=14:2x phase 2a: trimmed smoke done (smoke.make stages/SMOKE_STAGES, null noise anchor + TRIMMED reason, control cells default []; summary required stages, not_required, sealed once; CLI smoke-make flags optional)
- <=14:2x phase 2a: PR-C61-1 + C7d-2 done (services_of: engines.sheet_engines + manifest.Services whose LiveMath WorkerChecker follows the unit's tag-bound workers; session wrap ticketed I1-2)
- <=14:2x phase 2a: PR-C31-1 CLI part done (make_canaries -> evaluation.select_canaries; runcli.report Pause -> 3/5; recover 'release <scan sha>' + usage; monitor root_scans)
- <=14:2x phase 2a: OPS1 supply provenance done (make-items searchqa sources: exclude_sha256, datasets_version)
- <=14:2x phase 2a (addendum 14:3x items 4-6): S3 own run unit (smoke_roles.own_run, <root>/units/S3), detector on its parent trajectories, S3_GLM_CAP 2M, S-E6 GLM projection (MAX_ROLE_CALLS) + S3 cells in the ratio denominator; S2 ledger/leftover rows tolerate the concurrent S3 process; C7d-1 BUILT_STAGES + rehearsal S3
- <=14:2x phase 2a: ticket P2-A1-1 applied (tests/test_execskill_engines.py two lines)
- <=14:2x phase 2a tests: manifest+smoke+cli+runcli+engines 88 passed; smoke_roles 9 passed (12.6 s); rehearsal 9 passed (122.8 s)
- 14:30 phase 2a: P2-A3-1 applied (recover -> evaluation.release_check; own RELEASE/_release removed; monitor root_scans give hits/paused/decided/record_sha256); CLI tests on P2-A3's messages
- 14:30 phase 2a: PR-C31-2 via P2-A3-2 (e2e fixture registers S0 + read canaries with pool pins; optional scan assertion) and P2-A3-3 (integration_b5) applied; PR-C12-2 items 1-2 (e2e docstring, mutation entries)
- 14:30 phase 2a: mutations 31-36 added (31 run-root scan, 32-33 no-workbook probe, 34-36 read-record skip and release); -k subset 6 passed (each mutation fails its named test)
- 14:30 phase 2a: tests cli+b5+canaries+evaluation+manifest+smoke+runcli+engines 123 passed; e2e 11 passed (332 s)
- 14:30 phase 2a: smoke-runbook.md rewritten for the trim (S2 || S3, S-E6 GLM, stopped units, C7e-2 rule, C7c-2 row per C7e, 6.4 optional S-N1/S4, section 5 field shapes = 14:10 row 12 doc part); ticket I1-2 written (step._build checker session)
- 14:30 phase 2a: coordinator's extra tickets: P2-A2-1 option A (readout answer_tag_share None without tag_present) + aliases readout.windows/evaluation.completion_tokens + 1 test; P2-A3-4 (pilot-runbook 7.4 release wording, 2.7x); recover docstring wording; readout+acceptance+evaluation+canaries+cli 107 passed
- 14:30 clock note: the lines labelled "<=14:2x" were first written as "14:5x", an estimate; the dl clock read 14:30 at this line.
- 14:32 phase 2a: final smoke_roles+rehearsal+smoke+manifest+runcli+engines+integration_b5 77 passed (126 s); notes/I1-phase2a.md written; phase 2a done
- 14:3x phase 2b started (coordinator brief; registrar addendum 14:4x read). Part (a) avoids P2C's files (chain.py, protocol.py, scripts/run_execskill.py, tests/test_execskill_mutations.py, chain/e2e/integration tests).
- 14:42 phase 2b (a): 14:4x point 3 (smoke.LEAKAGE_CALLS = 6, DESCRIBER_CALLS = 3, cited) and point 4 (GLM next reservation at max(measured, ROLE_INPUT_BYTES)); tests updated (smoke, rehearsal)
- 14:42 phase 2b (a): acceptance.py on readout.windows / evaluation.completion_tokens; ticket I1-2 applied (step._build checker session) + test in test_execskill_manifest.py
- 14:42 phase 2b (a): row 12 tests' manifests (given(): card texts, contracts {text, sha256(text)}, sheet_qualification {path, record_hash}); manifest.check refuses hash/blank/missing cards (+1 test); smoke-runbook updated for 14:4x
- 14:57 phase 2b (a) done: fresh copy (/tmp/i1-copy-a, deleted) rehearsal+smoke_roles+smoke+manifest+step+acceptance+readout+canaries+runcli 140 passed (315 s); services_of docstring now states I1-2 applied. Live-tree rehearsal errors (9, "S-E6 reads the recorded stage S2") came from code files changing mid-run (code-map verify), not from a defect. P2C not finished (next: acceptance.finished_round, CLI, tests) -> (b) brief report; waiting for "P2C done" for (c).
- ~15:1x phase 2b (c) started ("P2C done"): registrar 15:0x (manual smoke path S0/S1 only; probe --fake; confirmation reservation runbook line), 15:1x (consent written), 15:3x (tickets P2C-1, P2C-2).
- ~15:4x phase 2b (c): P2C-1 (step.run_unit_spec -> chain.confirmation before anything is touched; step-unit declares first_call_caps too), P2C-2 (chain.read_budget prices the read units still to run by data.test_read_terms; read_estimate_record/test-read-estimate carry terms; manifest.setting_of refuses terms of another estimate), 15:0x CLI items (MANUAL_STAGES, probe --fake with ProbeGateway, smoke-make --probe-root, smoke.REHEARSAL_EVIDENCE labels, rehearsal_roots), tests updated; fresh copy rehearsal+smoke_roles+step+e2e+b5 41 passed (562 s).
- ~16:0x-16:4x phase 2b (c): registrar 15:5x R1-R6 verified in code: R1, R2, R3, R4, R5, R6 (a), (b), (d), (e) confirmed and fixed (one test each); R6 (c) not applied as worded (would strand interrupted attempts) -> ticket I1-3. R7 decision 16:1x applied: R7a (ENGINEER_CALLS per step, Context.spent), R7b (role caps 2.5M/3.0M/4.6M, budgets docstring 10.1M, runbook cap table), R7c (LEAKAGE_CALLS = 10, ENGINEER_REQUEST_FLOOR 225,170 -> 968,264).
- 16:4x phase 2b (c): mutation entries 56-77 added (P2C-1/2, 15:0x checks, R1-R3, R5, R6 a/b/d/e, R7a x3, R7c) and entry 48's site moved to `part`; -k subset (48 + 56-77) 23 passed (125 s).
- 16:5x phase 2b (c): pilot-runbook (header, rows 7/8/9, §2 go check accepts exactly shared/consent.json (+ test-canaries on a retry) and checks it valid, §3.2/§3.3 test_read_terms + evidence assert, §3.4 relaunch rule, §3.5 confirmation reservation line, §4, §5.4, §6.2, §6.3 step-unit + recover-only-when-idle (I1-3), §7.1 consent already written, §7.2) and smoke-runbook (open items, manual path, §4 stale S1 line removed, §6.3, §8 terms, new §9 CLI rehearsal) updated; ticket I1-3 written; CLI rehearsal test added (test_execskill_cli.py); rehearsal test's engineer reservation updated for R7c.
- 17:0x phase 2b (c): CLI rehearsal test passes on a fresh copy (52 s; S2 and S3 passed as two processes; summary passed; fixture estimate written). Fresh-copy whole suite: 1221 passed, 11 errors, all e2e: both chains paused at s1-spreadsheetbench/engineer ("A stored SpreadsheetBench trajectory of a known item") -- my R2 rewrite keyed the publics by bare item id, trajectories carry rounds.key. Fixed (keys), R2 test now uses item keys, mutation 66's site updated. Mutation suite (78 entries) passed before the fix; both suites re-running on fresh copies.
- 17:4x phase 2b (c) done: after the R2 fix, fresh-copy whole suite (55 execskill modules except mutations + test_coevo5_core + test_weak_solver_probe) 1232 passed (1036 s, e2e included), no bytecode written; mutation suite 78 passed (216 s); --help 35/35. /tmp/i1-* deleted on dl and the Mac. notes/I1-phase2b.md written; tickets P2C-1/P2C-2 status added; I1-3 open (R6 (c)).
- 19:15 integration phase M started (single writer): Codex round NOT ACCEPTABLE; owner replaced the pilot by the five-bench `main` (SQ->OQ->LM->SB->ALF, /data/execskill-20261022-main, route B for chain D). Tasks: (1) fresh-copy whole suite + minimal fixes, (2) mutations 1-110 + docstring ranges, (3) new five-step fake e2e under main incl. balance_exhausted -> switch-route B -> recover -> continue and G's record-only cost check, (4) CLI rehearsal (throwaway roots) incl. test-read-estimate --configuration main + make-manifest main, (5) runbooks vs code, (6) report + operator command list. Reading M-coordination, M-*.md, registrar 17:0x+.
- 19:4x integration M (1): fresh copy /tmp/i1-gate-m1 (pre-edit tree), whole route-B suite 1340 passed, exit 0 (no
  integration failure). Loose ends fixed in the dev tree: mutation entry 57 re-pointed to
  `require(found["identity"] == identity and found["passed"] is True,` (chain.confirmation after M4); evaluation.
  sealed_cell carries `solver_route` and unseal's per-cell projection passes it on (M4's request; routes test
  asserts it); S-E6 main self-test pricing VERIFIED correct (smoke._scope_cells lists MAIN_SCHEDULE_CELLS' earlier
  benches per self-test row, se6_projection prices each bench's cells at its own per-cell tokens and reserves the
  dearest bench's 4 x (bytes + 512 + B) with each chain's own B) -- no code change, a check added to
  test_m1_se6_projects_... (step 5's self-test per bench + chain D's B per bench); mutation docstring covers 78-110.
  Targeted rerun on /tmp/i1-gate-m2: routes+evaluation+evaluation_sheet+smoke_rehearsal+readout+b5+canaries 118
  passed. 19:47 mutation suite started on /tmp/i1-gate-m2.
- 19:51 integration M (2): mutation suite on /tmp/i1-gate-m2: 111 passed (entries 01-110 + 27a/27b; each site once,
  each named test passes unmutated and fails mutated) in 226 s. Next: (3) the five-step main e2e.
- 20:0x integration M (3): tests/test_execskill_e2e_main.py (new, engineering fixture): both chains run main's five
  steps SQ->OQ->LM->SB->ALF on fakes (small slices via supply.registered_sizes; BAND_PROBE_ITEMS 4), accept SQ/OQ/LM/SB
  and release ALF (selection only, no surviving change), freeze, consent present, five-unit read (OQ real, four
  stand-ins). Chain D pauses balance_exhausted on route A (HTTP 402) at s2-officeqa run attempt-1, real CLI
  switch-route --to B + recover, rebinds route B (confirm-route-B.json), redoes the unit there (D:redo settled), and
  its sealed test cells carry solver_route B; chain G's cost check records ok false, pauses false. 9 passed in 175 s.
- 20:0x integration M (4): test_cli_rehearsal_... parametrized [default]/[main]; [main]: smoke pins configuration main
  + clients.routes, S0 -> probe --fake -> S2 || S3 -> SE6 -> summary, test-read-estimate --configuration main, then
  main-runbook 3.2/4 on a throwaway main root (RUN_ROOTS patched): pins, make-manifest --s0-pins, setting_of G/D with
  zero calls, consent. 2 passed in 112 s.
- 20:1x integration M (5): every $CLI command and flag of smoke-, main- and pilot-runbook checked against the parser
  (36 subcommands); fixed smoke-runbook 5 (chain D block reads S1's branch/longest from stages/S1.json; longest is
  null on branch E) and 9 (--configuration main; the [main] rehearsal and the e2e named); main-runbook 0/2/9 (open
  items answered by the registrar 19:1x: above_high recorded, not a stop in main; owner-continuation still needed)
  and 8.1 (solver_route is {"route", "model"}; sealed test cells keep it). J7 guard asserted in the e2e.
- 20:1x final gate, first try: /tmp tmpfs on dl ran out of inodes (254,962; my old basetemps ~133K, other builders'
  /tmp/c7b2-suite 47,770 + /tmp/pytest-of-root 44,923 + /tmp/c7b2-rehearsal 6,758): 437 errors, all ENOSPC. Deleted
  my old /tmp/i1-* dirs (now ~150K free). INTEGRATION FAILURE found while checking the snapshot shape: the real
  snapshot holds skillopt/, scripts/, tests/ only (prelaunch.SNAPSHOT_DIRS, smoke-runbook 2), and the mutation
  suite's copy fixture copied pyproject.toml unconditionally -> FileNotFoundError, 111 errors in S0's pytest row
  (zero-call-checks and s0-collect's pytest row both run tests/test_execskill_*.py). Fixed: the copy is conditional.
  Rehearsing prelaunch.zero_call_checks itself on a snapshot-shaped rsync copy (/tmp/i1-snap; TMPDIR and
  PYTEST_ADDOPTS tmp_path_retention_policy=failed keep it under /tmp/i1-* and inside the inode budget).
  test_coevo5_core.py on the fresh copy: 71 passed. --help of all 36 subcommands ok; frozen diff empty.
- 20:44 final gate: prelaunch.zero_call_checks itself (the S0 pytest row, its registered command) on a snapshot-shaped
  rsync copy: 62 files, 1 failed, 1389 passed in 1,516 s (route-B tests 1,279 + mutations 111; all 111 mutations fail
  their named tests on the snapshot shape). The one failure is my rehearsal's artifact: TMPDIR pointed at a root-owned
  755 directory, and test_safety_4's uid-65534 child cannot mkdtemp its call dir there (the real row runs with /tmp,
  1777); with TMPDIR at a 1777 directory tests/test_execskill_sandbox.py passes 35/35. smoke-runbook 3 gained the
  /tmp inode pre-check (df -i /tmp: IFree >= 160,000). Frozen diff empty, no tracked file modified, no __pycache__ in
  the dev tree, main consent unchanged (290 B, 18:06, d3c89a8f70ff249d). All /tmp/i1-* on dl and the Mac deleted.
  DONE (report to the coordinator).
