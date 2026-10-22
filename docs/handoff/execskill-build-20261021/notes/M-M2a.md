# M2a progress (Codex #4, #5, #7, #8, #9, #10)

Started 2026-10-22 18:12 (local). Owner files: step.py (`_Step.unit`, `_Step.solver`/`_cells` mixed-unit endpoint
selection, `_run` completion/settlement, `_build` rebuild loop, held-set line in `_slices`), units.py, registry.py,
cells.py, examiner.py (#9, #10), chain.py `heavy` only; their tests. Mutation numbers 94-101.

## Plan
- #4: `units.solver_endpoint(..., cell_bench=)` (client, M, B, timeout of the cell's bench; scopes of the step);
  `cells.Context.endpoints` {bench: endpoint} + `endpoint_of(bench)`; `step._cells` builds one endpoint per cell bench.
- #5: `chain.heavy(setting, bench, *more)` takes the strongest mode over every bench whose cells the unit runs;
  `_Step.unit(..., benches=)`; self-test passes its sets' benches. Two-chain concurrency test.
- #7: registry ownership = (unit, run_root); `_slices` held-set exempts only this run root's own units.
- #8: idempotent completion commit in `units.run_unit` (completion evidence `complete.json` in the attempt, before
  drain; recovery finishes drain + unit.json without repeating work); `_run` settles consumption via the commit.
- #9: band gate needs BAND_PROBE_ITEMS (30) probe items, else `insufficient_material`; step skips paid probes.
- #10: finding-keyed counter across the attempt's builds (persisted per build in the attempt).

## Status (19:1x, done)
All six findings landed with tests; mutation entries 94-101 added (all killed on a copy of the tree); entry 04
re-pointed after the #7 registry edit (M1's FYI), killed.

- #4 DONE. `units.solver_endpoint(..., cell_bench=)`: client, M, timeout and B of the cell's bench, scopes of the
  step/kind/attempt. `cells.Context.endpoints` + `endpoint_of(bench)` (strict when set; one model only); `_solve`
  sends each cell by its bench's endpoint. `step._Step.solver(cell_bench=)`, `step._cells` takes {bench: endpoint};
  `_selftest` builds one endpoint per set bench, one seeded interleaving, the step's `...:selftest` scope.
- #5 DONE. `chain.heavy_mode(benches)` (EX if any SB, SH if any ALF, else none); `chain.heavy(setting, bench, *more)`;
  `_Step.unit(..., benches=)`; `_selftest` passes its sets' benches.
- #7 DONE. registry: ownership = (label, canonical run root) (`run_identity`, `_owns`), `Registry.bound(run_root)`,
  moves take `run_root=`; the fold re-validates with each line's root; decided stays consumed. `_Step.unit` binds the
  registry to the run root. `_slices` held set exempts only this root's own labels.
- #8 DONE. `units.run_unit(..., settle=)`: work -> `completed.json` (completion evidence) -> `settle(attempt, result)`
  -> drain -> unit.json; after a pause/interruption with completion evidence the next attempt (owner decision) is a
  commit: settles again (idempotent `registry.decide`), drains, writes unit.json naming the worked attempt
  (`committed_in`), runs no work, no redo limit. `_run` decides the run slice in its settle callback.
- #9 DONE. `examiner.sufficient` (>= BAND_PROBE_ITEMS = 30 items); `band()` in band only on a full probe, `reason`
  `insufficient_material` otherwise; `gates()` records an insufficient set (`probe_items 0, pass_rate None`), never
  admitted; `outcome_counts` counts it; `_generate` probes nothing (band or shortcut) on an insufficient set.
  Engineering fixtures with 4-item sets scale the probe size explicitly (`monkeypatch.setattr(examiner,
  "BAND_PROBE_ITEMS", 4)`): step tests `build()`/`sheet_step()`, shortcut_sb C1-2, e2e pilot.
- #10 DONE. `examiner.build(..., derived=)` continues a finding-keyed counter (`Generated.derived`); `step._build`
  continues the attempt's latest persisted counter of the set and persists its own (`finding-counts-<n>.json`).
- Coordinator FYIs: W's C1-2 failure and M2b's four step failures were the #9 rule landing before the fixture knob
  (fixed); M4's manifest i1_2 AttributeError fixed (`_build` persists a counter only for an `examiner.Generated`).
- #8 on the accept unit (19:0x, logged cross-owner): accept/reject/small settle in a `settle` callback after the
  completion evidence; an undetermined decision still pauses inside the work.

Open: unbound registries (fixtures) still match moves by label. Commit attempts are exempt from the redo limit (they spend nothing). S-E6/caps (M1):
self-test cells now reserve with their own bench's B; the main schedule's self-test rows must list the earlier
benches' cells.

## Tests (dl, final code)
units 20, registry 9, cells 13, examiner 12, chain 35, rounds 6, shortcut_sb 6: 101 passed. step 21, fivebench_step 7,
acceptance 28, smoke_rehearsal 10: 65 passed + 1 failed (J7 test's `st.unit` fake lacked `**options`; fixed, fivebench_step
7 passed). manifest -k i1_2: 1 passed. e2e: 11 passed. Mutations 04, 94-101: 9/9 killed (named tests pass unmutated).
New tests: registry 1, units 3, cells 1, chain 2, examiner 2 (+ test_exam4/5/6, r6b adapted), step 7.
