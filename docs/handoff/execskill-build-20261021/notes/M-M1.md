# M1 progress (main configuration + #13 + main-runbook)

Started 2026-10-22 18:06 (M round). Spec: registrar "Owner instructions 2026-10-22 17:0x and 17:3x"; Codex #13.

## Status (resume from the first unchecked item)
- [x] protocol.py: `main` in PILOTS (= CONFIGURATIONS), MAIN, MAIN_ROOT/MAIN_MANIFEST, `main_real_run`, main's
      schedule cells and caps, TEST_READ_CELLS["main"], CONFIG_* lookups, COST_CHECK_PAUSES, REAL_RUN_EVIDENCE,
      RUN_ROOTS, `first_call_bench`, `configuration_of(setting)`, `order_of(setting)`
- [x] budgets.py: `chain_caps`/`caps`/`role_scope_caps` per configuration
- [x] manifest.py: field `configuration` (make keyword, default PILOT; check: known, caps equal, real-run label);
      `_pools` by the configuration's order; `setting_of` -> extra["configuration"], extra["searchqa_tail"]
- [x] chain.py: order/caps/first-call bench by configuration; cost check record-only in main; read estimate by the
      S-E6 record's configuration
- [x] step.py (cross-owner, logged): parent_of, run_unit_spec, cost_projection factor
- [x] evaluation.py (cross-owner, logged): read canaries' pools check by the configuration's order
- [x] smoke.py: S-E6 projects m["configuration"] (schedule, caps, GLM), records `configuration`
- [x] s0.py #13: fenced copy program, `invalid` verdict, cards/runtimes required + recorded, FakeNative in fakes
- [x] run_execskill.py: make-manifest `configuration` (+ real-run root check), export-pools ALF from fresh supply,
      make-items via supply.views_record, test-read-estimate --configuration, s0-collect --texts/--sheet-runtime
- [x] tests: protocol (main caps from calc), manifest (main manifest), chain (main run, record-only check,
      cost projection), cli (pins updated, export-pools ALF)
- [x] tests: smoke S-E6 main (+ rehearsal on a main smoke manifest), cli test-read-estimate main + make-manifest
      configuration/root + s0-collect --texts/--sheet-runtime, budgets main, s0 direct equivalence (invalid verdict)
- [x] mutation entries 88-93 (each site once; each named test passes unmutated and fails mutated on a /tmp copy)
- [x] main-runbook.md; smoke-runbook status, §3 (s0-collect --texts/--sheet-runtime, export-pools ALF from the fresh
      supply), §5 (configuration main, clients.routes), §6.2, §7, §8
- [x] targeted run 19:07: protocol+budgets+manifest+chain+smoke+s0+cli+runcli+canaries 217 passed; rehearsal+routes
      +fivebench_step 62 passed, 1 failed (M2b's J7 test vs step.py `st.unit(..., settle=)`, not M1's); frozen diff empty
- [x] final report (19:1x); open: registrar items in M-coordination 19:1x (above_high in main, continuation file)

## Cap arithmetic of `main` (registrar 17:0x: every cap >= 3 x its computed maximum need)
Need of a step scope = its maximum-schedule cells (calc T4 `step_cost` with main's step arguments, see
tests/test_execskill_protocol.py MAIN_STEP_ARGS; LiveMath acceptance + J7's 64 + 64 cells) at the §9.1 high anchors
(card x 1, procedure x 1.6) + 16 full chain-G reservations 4 x (calc request bytes + 512 + 65,536) = 520,192 (QA, SB),
392,192 (ALF). Cap = ceil0.1M(3 x need).

| step | run | examiner | selftest | accept |
|---|---|---|---|---|
| searchqa | 29.9M | 26.5M | 28.2M | 110.7M (need 36,883,072) |
| officeqa | 28.7M | 38.7M | 34.2M | 83.0M |
| livemath | 29.6M | 36.3M | 35.7M | 56.1M |
| spreadsheetbench | 27.6M | 33.3M | 39.1M | 43.8M |
| alfworld | 44.8M | 38.3M | 72.0M | 201.1M (need 67,025,072) |

- redo reserve 72.0M = ceil0.1M(3 x 23,982,336), the dearest single redo (ALFWorld's self-test); every attempt
  sub-scope min(kind cap, 72.0M) >= 3 x its redo (asserted in the protocol test)
- test read 407M = ceil1M(3 x (93,975,624 max read at the high anchors + 5 units x 16 x 520,192 = 41,615,360)
  = 3 x 135,590,984 = 406,772,952); 1.3 x the high estimate (77.3M) fits
- solver 1,520M = ceil5M(steps 1,037.6M + 407M + 72M = 1,516.6M) >= 3 x (summed needs 505.05M)
- GLM 288M = 3 x 5 steps x (5M + 5M + 9.2M); overall 1,808M per chain
- chain D: B <= 65,536 on both routes (route B branch N), so its reservations never exceed chain G's: same caps
