# C7e: a paused acceptance redoes ONE block (registration §9.3, owner decision #15). Closes ticket C7c-2.

Agent C7e, 2026-10-22. Protocol fivebench-execskill-v1, route B. Build tree `/data/execskill-dev` (the Mac mount
`/Users/dulin/remote/dl`). I made no model call, used no network, ran no docker and wrote nothing to git. I read no
test pool and wrote nothing under a real run root. Frozen code is unchanged.

## Status

| Item | State |
|---|---|
| One-block redo in `acceptance.dispatch` / `step._accept`, with a sealed block → attempt map in the decision | done, tested |
| Budget: the redone block goes to `...:accept:attempt-N` and `<chain>:redo`; the blocks no attempt started go to `...:accept` | done, tested |
| OfficeQA's 2-hour gap between every two blocks of the round, whichever attempt ran them | done, tested |
| S4 drill: the `redo` and `sealing` rows check the one-block redo; rehearsal expectations | done, tested |
| Mutation checks (splicing, reusing a partial block, wrong endpoint, whole-round redo) | done: each one made tests fail |
| **Ticket C7c-2** | **closed**: choice 1 of the ticket, as registered |

## The rule and where it is built

The rule comes from four places:

- Registration §9.3 (line 867): "每次重做用自己的子作用域（`…:accept:attempt-N`），重做预留单列；SearchQA、OfficeQA、ALFWorld
  的验收分块，暂停只重做一块".
- Owner decision #15 (line 1033, 【默认已生效】): "整块重做，不把不同时段的格拼在一起（时段漂移最大 22–24 分）".
- Plan §5 recovery: "a redo re-dispatches the whole block … no splicing across attempts".
- Calc T6 (line 1569): the attempt-N cap is min(kind cap, redo reserve), and the redo reserve is "the largest single
  acceptance block cap (one redo pre-funded; a second redo needs the owner's recorded cap decision)". Line 810 says
  the same: "重做 ≤ 2 次（第一次由重做预留支付，第二次要负责人在 `recovery.json` 里写明上限决定）".

| Rule | Code |
|---|---|
| A block an earlier attempt completed is kept | `acceptance.earlier_blocks` (acceptance.py:357). A block counts as complete when ONE earlier attempt holds the finished record of every scheduled cell (`_finished`, :345). A finished record is sealed, not stopped and judged; it matches the job's set, item, run, arm and block; and its `unit_attempt` names that attempt. The first such attempt is used. A record with a broken seal raises. |
| The paused block is redone whole | A block that is not kept, where an earlier attempt claimed or stored any cell (`.claim` or `.json`), goes to `"redone"`. The new attempt runs all of its cells into its own `cells/`. No earlier record of that block is read again. |
| The other blocks run after it | `acceptance.dispatch` (:238) runs the blocks in schedule order and skips the kept ones. It returns kept and new records, block by block. |
| A block's cells always come from one attempt, and nothing is spliced | `runner` (:299) writes `unit_attempt` into every cell (:319). `decide` calls `_provenance` (:391, :646), which refuses a round with a missing, doubled or foreign cell, or with a block that holds cells of two attempts. The decision record carries `provenance: {block: {attempt, cells, cells_sha256}}` (:720), sealed by the record hash. |
| The decision can be made again | `round_cells(unit_root, sealed, decision)` (:759) reads each block's cells from the attempt the map names. `reproduce(round_cells(...), sealed, decision)` (:753) is True. |
| Each redo has its own sub-scope; the redo reserve is listed separately | `step._accept` (step.py:786). The redone block runs through `st.solver("accept", attempt)`, which charges overall, `c:solver`, `c:redo` and `...:accept:attempt-N` (`budgets.solver_scopes`). The blocks no attempt started run through `st.solver("accept", attempt, first_run=True)`, which charges `...:accept` (`units.solver_endpoint(first_run=)`, units.py:95). |
| OfficeQA's two time blocks are ≥ 2 h apart (§3.3) | `dispatch`: the gap before the first block the new attempt runs is counted from the last `finish_ts` of the kept blocks. Later gaps work as before. |

### Why the budget is split this way, and how it matches T6 and S-E6

If every block attempt N runs were charged to `...:accept:attempt-N`, the C7c-2 failure would come back. An OfficeQA
pause inside block 1 makes attempt-2 run both blocks, about 19.3M at the maximum schedule, and its cap is 14.8M.

With the split:
- The sub-scope holds exactly one block. That equals T6's attempt-N cap and `smoke._scope_cells`, which prices
  attempt-N as accept cells / `SLICES[bench]["blocks"]` (smoke.py:1066-1071).
- `c:redo` holds one block per redo, which equals S-E6's redo reserve (the dearest single block). A second redo of
  another block exceeds it and needs the owner's `raise_cap`, as registered.
- The kind scope `...:accept` holds attempt 1's sends plus the never-started blocks. That is at most one whole round
  (the wasted part of the paused block plus the later blocks), so the kind cap holds.

The step test checks this split on chain G's ledger.

## What changed (C7e's edits only)

- `skillopt/execskill/acceptance.py`:
  - module docstring :44-54;
  - imports :71 (`ATTEMPT`, `attempts` from the frozen coevo5 evaluation) and :73;
  - `dispatch` :238-279 (`attempt`, `earlier`, `redo`, the gap after kept blocks);
  - `runner` :299-327 (`unit_attempt`);
  - new section "a redo" :329-418: `unit_attempt`, `_job_key`, `_cell_key`, `_finished`, `earlier_blocks`,
    `_attempt_number`, `_provenance`;
  - `_balance` :526-568 (the duration is summed per unit attempt, plus `attempt_spans`);
  - `decide` :646 and :720 (`provenance`);
  - `reproduce` docstring :753;
  - new `round_cells` :759-775.
- `skillopt/execskill/step.py`:
  - docstring 5.6 :39-50;
  - `_Step.solver(..., first_run=)` :195-201;
  - `_accept.work` :792-850: two endpoints, `earlier_blocks`, a `redo` runner from attempt 2 on, `dispatch(...,
    earlier=, redo=)`, and the unit result's `provenance`, `reused` and `redone`.
- `skillopt/execskill/units.py`: docstring :21; `solver_endpoint(..., first_run=False)` :95-110 (accept only).
- `skillopt/execskill/budgets.py`: docstring :22-27 only. The scopes did not change.
- `skillopt/execskill/smoke.py`, S4 only:
  - docstring :57;
  - import :93 (`Pause`, `cell_id`);
  - `s4_judged` :1219-1300. The cells come from `acceptance.round_cells`. The `redo` row also requires `one_block`.
    The result adds `drill.block`, `blocks`, `reused`, `redone` and `provenance`.
- Tests:
  - `tests/test_execskill_acceptance.py` :513-714 (fixtures `BLOCKS3`, `Clock`, `stored_run`, `three`; 5 tests);
  - `tests/test_execskill_units.py` :130 (1 test);
  - `tests/test_execskill_step.py` :462-535 (1 test, the full OfficeQA step);
  - `tests/test_execskill_smoke_rehearsal.py` :150-160 (the S4 expectations).

## The S4 drill: what happens

`protocol.S4_DRILL_CALL = 50` stops attempt-1 inside block 1 of the round's four SearchQA blocks (40 accept items,
10 per block). No block is complete, so nothing is kept. After `smoke-recovery`, attempt-2 does three things:

- redoes block 1 whole on the smoke chain's `...:accept:attempt-2` and `...:redo`;
- runs blocks 2-4 for the first time on `...:accept`;
- decides from attempt-2's cells only (provenance: all four blocks in `attempt-2`).

The `redo` row checks this exactly: kept = the blocks before the drill's block (none), redone = [b1], and the same
provenance in the unit result and the decision. The drill does not exercise keeping a completed block. The unit tests
cover that: the acceptance tests pause in b2 of 3, and the step test runs a full OfficeQA step. The protocol.py:343-345
comment ("the redo re-dispatches it whole") is still true in effect, because every block runs again in attempt-2. If
the registrar edits protocol.py, the comment could say "redoes block 1 whole and runs blocks 2-4".

## Tests (dl, `PYTHONDONTWRITEBYTECODE=1 $PY -B -m pytest -q -p no:cacheprovider`)

| What | Result |
|---|---|
| New C7e tests: acceptance 5, units 1, step 1. The S4 rehearsal assertions were updated. | all pass |
| acceptance + units + step + smoke | 68 passed (120 s) |
| `tests/test_execskill_smoke_rehearsal.py` | 8 passed (110 s) |
| Whole route-B suite `tests/test_execskill_*.py` (1075 collected), 13:00-13:12 | **1062 passed, 2 failed, 11 errors** (686 s) |

All 13 non-passing results come from another agent's work in progress (PR-C31, ticket C3-1, run-root canary scan in
`evaluation.py`, started 12:40). None is in a file C7e touched:
- The 11 e2e setup errors and `test_execskill_integration_b5.py::test_chains_g_and_d_read_once_then_unseal_and_read_out`
  stop in `evaluation.unseal → _root_scanned → _canary_records`: "No registered test canaries in the run root".
- `test_execskill_canaries.py::test_the_root_scan_reads_decoded_json_...` is PR-C31's new test (`files == 8` is 9).

The e2e fixture ran both chains through every unit, including both accept units, to the unseal, so the accept path
did not raise in the full pilot. **The e2e assertions themselves (decision again from the records, the ledger per
scope) did not run.** I1 phase 2 should re-run `tests/test_execskill_e2e.py` once PR-C31 has registered the canaries
in its fixture. I did not bypass the scan in a copy.

Mutation checks were done in a throwaway copy, `/tmp/c7e-mut`, which has been removed. Each mutation made tests fail:
- M1 reusing a partial block (`all` → `any` in `earlier_blocks`): 4 acceptance tests fail.
- M2 splicing (keep the redone block's finished cells and run only the missing ones): 5 tests fail, including the
  step test with "A block's cells come from one unit attempt".
- M3 never-started blocks on the redo endpoint: the step test fails (ledger 792 ≠ 408).
- M4 whole-round redo (`earlier=None`): the step test fails (b1 from attempt-2, not attempt-1).

Static check: `ruff --select F,E9` on the changed files reports only the existing fixture-import idiom
(`workers`, F811) in `test_execskill_step.py`. No new line is longer than 120 characters.

## Deviations and choices (for review)

1. **Budget split** (above). Only the redone block goes to the sub-scope and `c:redo`. The blocks attempt N runs for
   the first time go to the kind scope. The task asked that the attempt sub-scope cover "only what that attempt
   runs"; this keeps it narrower than that, at one block.
2. **"Redone" means started and not complete in an earlier attempt** (any `.claim` or `.json`). A pause before the
   first claim of a block, for example in OfficeQA's gap, charges no redo reserve, and the next block runs on the
   kind scope.
3. **J5 balance duration** (§6.2, the 5 % band): the sum over unit attempts of first dispatch → last finish. A
   multi-day pause between attempts therefore does not widen the band. With one attempt nothing changes.
4. **The gap after a kept block** counts from its last recorded `finish_ts`. The registered ≥ 2 h holds between every
   two blocks of the round.
5. **Record contract extended.** Every acceptance cell's `cell` gains `unit_attempt`, and the decision gains
   `provenance`. No real decision exists yet. An attempt written before C7e (no `unit_attempt`) is never kept, so
   its block runs again whole.
6. **A finished round is never re-run** (J5/J6 `acceptance_undetermined`, or a `decide` error after the last cell):
   the redo keeps every block and gives the same result. This needs an owner decision: ticket **C7e-2**.
7. Readers of a redone round's accept cells must use `acceptance.round_cells`. Globbing the last attempt's `cells/`
   misses the kept blocks. `s4_judged` uses `round_cells`. The e2e test globs, which is fine for its single attempt.

## Observations and tickets

- **C7e-1** (registrar): G_acc cells are charged to `...:accept` (and, in a redone block, to the redo scopes), but
  §3.3 (line 320), §9.2 (line 807) and T6 register them in the examiner scope. OfficeQA at the maximum schedule: the
  accept margin falls from 1.53x to 1.32x, one block's from 1.53x to 1.33x of the redo reserve. Every cap still holds.
- **C7e-2** (owner): a redo after `acceptance_undetermined` (or a decide error after the last cell) reproduces the
  same result. Is a fresh round wanted? It would need a v1.1 rule and a whole-round cap.
- ALFWorld (recommended pilot only, not chosen): blocks are whole rooms (`step._blocks`, step.py:755-761), with equal
  room counts, not equal game counts. One block can therefore hold more than a quarter of the games, while the redo
  reserve and S-E6's attempt-N pricing assume a quarter. SpreadsheetBench (1 block) and OfficeQA (2 equal halves) are
  exact.

## For the integrator (I1 phase 2)

- Runbook §0, line 21 (C7c-2 row). Suggested replacement: "An acceptance redo keeps the blocks an earlier attempt
  completed, redoes the paused block whole on `...:accept:attempt-N` + the redo reserve, and runs the remaining
  blocks on `...:accept` (§9.3, owner decision #15; C7e). The S4 drill stops in block 1, so attempt-2 redoes b1 and
  runs b2-b4; nothing is kept. | Closed by C7e. | C7c-2 (closed), C7e-1, C7e-2"
- Re-run `tests/test_execskill_e2e.py` after PR-C31 (see Tests).
