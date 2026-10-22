# Ticket fixer-6 → main agent (step.py, examiner.py, A13-1 adapters): contracts the fixer added

From the fixer (2026-10-22). Isolation review findings 1, 5, 6; statistics review findings 2, 3, 4;
safety review findings 2, 6. Tickets A12-2 and A13-1 stay open. `step.py`, `examiner.py`, the
`run_unit_spec` / `report` adapters and the e2e test still do not exist, so these contracts are tested only module
by module.

What the missing code must do with the fixed modules:
1. **Acceptance (statistics 2-4).**
   - Dispatch through `acceptance.dispatch(..., clock=, sleep=)`. It waits out `protocol.BLOCK_GAP_SECONDS`
     (OfficeQA: 2 h) between time blocks.
   - After `acceptance.decide(...)`, call `acceptance.settle(decision, sealed, registry, items)`.
     - On "undetermined" it raises `cells.Pause("acceptance_undetermined", ...)`: the unit pauses, and the batch
       counts as consumed but undecided (§13).
     - Only accept and reject mark items as decided.
   - J5 now includes `block_gap` and sets `pause`. J6 checks every registered duplicate pair.
2. **Engineer payload (isolation 5).** `engineer.Context` refuses any trajectory that is not a verified run unit
   (`<chain>/s<k>-<bench>/run`) of the label's chain and bench, from step k or earlier. It also refuses:
   - references on ALFWorld, or for items that did not fail;
   - detector input other than `detectors.counts(...)`;
   - a `previous` that is not the decision/faults/format summary.
   Build the payload from run-slice cells only.
3. **Examiner (isolation 6).** Use `detectors.examiner_diagnosis(halves, bench=...)`, which takes the write half
   only and refuses hold-half cells. `detectors.diagnosis` is for the engineer only.
4. **Masked views (isolation 7).** `trajectories.masked_view` masks restated answers, and LiveMath option letters
   and text through `choices=task["choices"]`. Pass the task record, not a stripped copy.
5. **Ledger bound (safety 2).** `manifest.check_clients` now requires each solver block's B to equal
   `solver_block(...)` re-derived from its recorded `branch` and `longest`. The adapter must fill `Setting.branch` /
   `Setting.longest` from the **verified manifest's** `clients.solver["D"]` block. `units.solver_endpoint` derives
   the bound from those fields, so it is the manifest's B only if the adapter copies them. Suggested assert in the
   adapter: `ledger_bound(model, bench, branch=setting.branch, longest=setting.longest) == block["B"][bench]` for
   every bench. Still open: the S1-b result's sha256 is not bound into the solver block.
6. **Test read (isolation 2, 3, 10-12).** The `evaluate-unit` adapter calls `evaluation.evaluate(...)`:
   - without `reset` (the unit builds the ALFWorld reset itself);
   - with `canaries=evaluation.load_canaries(root)` (see fixer-4).
   The owner's addendum is sealed with `evaluation.seal_addendum` (see fixer-1).
7. **Safety 6 invariants** (the review's list, unchanged): `Setting` refuses slots not built by `slots.pools`;
   `Worker` refuses `live=None` / `per_call=None` outside tests; every unit takes `heavy(setting, bench)`; ALFWorld
   units run with 6 workers.
