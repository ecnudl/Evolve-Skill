# Integration B3 (cells, rounds, acceptance): rows A8 and A9 wired together

Integrator B3, 2026-10-22. Rows A8 (`cells.py`, `units.py`, `rounds.py`, `trajectories.py`) and A9 (`donors.py`,
`placebo.py`, `acceptance.py`, `validity.py`). Registration `execskill-registration-v1-20261021.md` wins over the
plan. No model call, no container, no test-pool data, no state-changing git. Everything here is an engineering
fixture (`engineering_fixture`); nothing is evidence of a method effect.

## Gate (ii): PASS

`tests/test_execskill_integration_b3.py::test_gate_ii_a_fake_acceptance_round_reproduces_its_decision_from_the_cell_records`
runs one fake OfficeQA acceptance round end to end. It uses a stateless fake solver behind the frozen `Endpoint`,
FakeSandbox procedures, one worker thread and a tick clock. Every cell is a real `cells.run_cell`: the shell, the
frozen call wrapper and scorer, the route-B decision rows and the judge.

1. **Run slice.** The parent S runs on 12 run-slice items x 2 runs = 24 cells as a unit (`units.run_unit` +
   `rounds.run_round`). Its stored parent trajectories (`trajectories.load_run`, filtered on `arm_kind == "parent"`)
   are the donors.
2. **Sealing.** `acceptance.prepare` seals the round with zero model calls: A = 40 items in 2 blocks of 20. The
   parent package is K + D. The candidate S' is K + N: a new procedure N and the deleted D, so both twin kinds occur.
   A* = 30, with twins `withhold:N` on 15 items and `restore:D` on 10. P_y and P_i are present, G_acc has 10 items,
   and S_dup is present. The P_y sham of N is a donor's note, not the item's own note.
3. **Dispatch.** `acceptance.dispatch` runs inside the acceptance unit with `acceptance.runner` (new, below). It
   produced 870 cells, all of them sent in the order `acceptance.schedule` gave:
   - real cells: 6 arms x 30 items x 4 runs = 720, plus 60 withhold and 40 restore twin cells;
   - G_acc cells: 5 arms x 10 items = 50.
   Each cell has a trajectory and an enable-log line. Each cell's `package_sha256` is the sealed package of its arm,
   and its `arm_kind` is the one `cell_arm` gives. The fake solver was called exactly once per cell.
4. **Decision.** `accept`, reason "J1-J7 hold":
   - S'-S, S'-P_y and S'-C: mean 0.50 each, whole batch 0.375, one-sided p_t 2.6e-6, sign-flip p 2.0e-5 with the
     registered 100,000 draws, bootstrap with 10,000 draws.
   - P_y-S, P_i-S and S-C: 0. Placebo rule `informative`.
   - J3: 0 fault items. J4: 0 vs 0, margin 2.
   - J5 balance: spread 6 s of 1,739 s.
   - J6: S_dup-S, p = 1.0.
   - tau(N, withhold) = 0.333 and tau(D, restore) = 0.
   The registry ends with A* `decided` and A \ A* `routed_not_dispatched`. `validity.round_pair` gives n_gen = 10,
   with d_gen > 0 and d_real > 0. `validity.dup_control` gives both intervals as [0, 0].
5. **Reproduction.** The cell records are read back from `<attempt>/cells/*.json`, the sealed record from
   `sealed.json` and the decision from `decision/decision.json`. `acceptance.decide(cells, sealed)` on them gives
   byte-identical canonical JSON with the same `record_sha256`.

The test takes 21-22 s on dl with the registered draw counts; no count is patched.

The second test, `test_a9_1_a_step_one_sheet_parent_cell_stores_its_precheck_and_feeds_the_sheet_feedback_sham`,
checks ticket A9-1 end to end (0.03 s):

- a SpreadsheetBench parent cell at step 1 (the empty package, nothing enabled) pre-checks its program once and makes
  one logical call;
- the stored trajectory carries the report;
- `donors.donor_inputs` reads the report, and a candidate's new `sheet_feedback` procedure gives its advice on it in
  `donors.donor_corpus`, with zero model calls.

## pytest (dl, `PYTHONDONTWRITEBYTECODE=1 python -B -m pytest -q -p no:cacheprovider`)

- `tests/test_execskill_*.py tests/test_weak_solver_probe.py tests/test_coevo5_core.py`: **`781 passed in 57.69s`**.
  - route B: 691 tests in 28 files, including the 2 new ones;
  - frozen: `90 passed in 0.48s` (test_coevo5_core 71 + test_weak_solver_probe 19).
- Before the B3 edits: 779 passed (689 route B + 90 frozen).
- No `__pycache__` or `.pyc` under `skillopt/execskill`, `tests` or `scripts` afterwards.

## Files changed (each edit minimal; all whole-file tests above pass)

1. `skillopt/execskill/solver.py` `_solve_sheet` (ticket A9-1; registration §2.5). The shell pre-checked the extracted
   program only `if shell.enabled(("sheet_feedback",))`. Registration §2.5 says the shell pre-checks the program once
   on the public input after the first answer, stores the result in the cell record and reads it back on replay; it
   sets no condition. The pre-check now runs for every extracted program. With no enabled `sheet_feedback` procedure,
   `shell.feedback` returns `("", False)` and nothing reads the report in the cell. The report is still stored
   (`shell.precheck`, trajectory `shell.precheck`), and it feeds:
   - the P_y `sheet_feedback` sham (§6.1 donors);
   - the mechanical category `program_exception_on_public_input` (§5.2).
   Cost: one more container run per SpreadsheetBench cell without an enabled `sheet_feedback`, and no model call. The
   request, the prediction and the T-SOLVER-1 projections are unchanged. A failed pre-check is a report (status
   unknown, `precheck.py:102-108`). Only an unconfirmed cleanup stops the run (`precheck.py:100-101`), as for every
   container run.
2. `tests/test_execskill_solver.py` T-SOLVER-1 SB and `tests/test_execskill_integration_b2.py` gate (i). The old
   assertion `native.prechecks == []` encoded the unregistered condition. It now asserts the registered count: one
   pre-check per program the shell extracts (12 and 2). `native.cases` and the projections are asserted as before, so no assertion
   was dropped.
3. `skillopt/execskill/donors.py` `donor_corpus`. It now refuses any trajectory whose `arm_kind` is not `parent`:
   - a run-slice unit also holds card-arm cells (§5.1), and A9-1 §3 says that only the parent's trajectories are
     donors;
   - the docstring contract now lists `arm_kind`.
   The synthetic donor fixtures in `tests/test_execskill_placebo.py` (`qa_trajectory`, `sheet_trajectory`,
   `alf_trajectory`) and `tests/test_execskill_acceptance.py` (`trajectory`) now carry `"arm_kind": "parent"`, the
   field `trajectories.build` writes.
4. `skillopt/execskill/acceptance.py` (ticket A9-2 request 1, A9-3 step 2):
   - new `round_packages` and `runner`;
   - `prepare` builds its sealed package table with `round_packages` (same keys and hashes as before);
   - imports `cells.Arm`, `cell_id`, `run_cells`;
   - module docstring updated.
5. `skillopt/execskill/rounds.py` module docstring. Training-side rounds use `run_round`. An acceptance round runs in
   `acceptance.schedule`'s order through `acceptance.runner`.
6. `tests/test_execskill_integration_b3.py`: new, 2 tests (above).

## Public API added

- `acceptance.round_packages(candidate, parent, *, step, twins) -> {key: Package}`. The arms' packages are keyed as
  `cell_arm` names them: `candidate`, `parent`, `card` (the step's empty package), `placebo`, and `restore:<id>` per
  restoration twin. The dispatch driver rebuilds them with `step=sealed["step"]` and
  `twins=sealed["plan"]["twins"]`, and `prepare` seals their hashes.
- `acceptance.runner(context, sealed, packages, tasks, *, workers, store) -> run(block, jobs)`. This is the `run` of
  `acceptance.dispatch`, and it begins with `check_packages`. Each job becomes the cell `{id: cell_id(unit, arm, item,
  run), unit, arm, benchmark, task_id: item, run, set, block, source_item}` with
  `Arm(arm_kind, packages[key], **keywords)` from `cell_arm`. The block's cells run through `cells.run_cells` in the
  schedule's order, never re-ordered. `tasks` must hold the A* items, the G_acc items and the probe items.

## Checked across the rows (matched; no change)

- **Top-level cell fields.** `cells.run_cell` copies `arm`, `task_id`, `run`, `set` and `block` to the record's top
  level (`ROUND_KEYS`). `acceptance` reads them, plus `judge.v2.token`, `judge.format.violation`, `judge.flags`
  (`reasoning_mismatch`), `faults[].procedure`, `logical_calls[].purpose` (first/second/repair/step),
  `worst_delivery` (`outcomes_ext.DELIVERED`), `sends`, and `dispatch_ts`/`finish_ts` (epoch floats).
- **Faults.** Shell faults and routing faults both carry `procedure`, so J3 counts changed procedures from either.
- **Arm kinds.** `cells.ARM_KINDS` with the `withhold:`, `restore:` and `gen:` prefixes accepts every `cell_arm` kind.
  A restore twin's package plus `restore=` and a placebo's `placebo=` dict pass the shell's checks: P_y and P_i ran
  in 240 real cells and 10 G_acc cells of the gate.
- **Donors.** `donors.donor_inputs` reads what `trajectories.build` writes: `cell`, `task_id`, `bench`,
  `calls[0].purpose == "first"`, `calls[].user`, `shell.precheck`, `alfworld_steps[].action`.
- **Tokens and statistics.** `rounds.tokens`/`table_of` and `acceptance.table` both read `judge.v2.token`.
  `stats_ext.item_scores` handles the L/H sides (`acceptance.side`).
- **Write-once records.** `sealed.json`, `decision/decision.json`, cell records and trajectories go through
  `continual_eval.core.write_json`, which is `validator_pilot.api.write_immutable_json`. A byte-equal rewrite is
  allowed and a different one refused.

## Frozen code relied on (read-only; dl copies byte-identical to the mirror, checked with `cmp`)

- `skillopt/coevo5/cells.py:84-85`: `cell_id` = digest of {unit, arm, task_id, run}[:32]. `:237-249`:
  `run_parallel`. Results come back in job order, and no job starts after an error, so `runner`'s order is the
  dispatch order.
- `skillopt/coevo5/step.py:79` (`_order`) and `:105` (`run_round`). This is the uniform shuffle that the acceptance
  round no longer goes through.
- `skillopt/continual_eval/core.py:60-61` (`write_json`) and `skillopt/validator_pilot/api.py:45-54`
  (`write_immutable_json`, byte-equal resume).
- `skillopt/coevo5/calls.py`: `Endpoint(client, *, model, max_tokens, slots, ..., sleep)` and `Slots(root, name,
  count)`, behind which the tests put their fake clients.

## Deviations

1. **A9-1.** I took option (a) because registration §2.5 already requires it. It applies to every SpreadsheetBench
   cell, not only to run-slice cells. If the main agent prefers option (b), the registrar's pre-check at sealing time,
   the solver change reverts and `donors.donor_corpus` needs a `precheck(trajectory)` callable.
2. **A9-2.** The acceptance driver calls `cells.run_cells` directly (`acceptance.runner`) instead of adding a
   keep-order mode to `rounds.run_round`. `rounds._order` is unchanged.
3. **A9-3 (MDE).** No MDE is registered here. Registration §3.3 gives approximate values (SB ~12, OQ ~10, ALF
   9.7-10.9, LM ~9-10 provisional, SQ ~3.4 provisional), and `stats_ext.mde(se, ...)` needs a measured SE. So
   `prepare(mde=)` stays the caller's. The gate passes 0.10 for OfficeQA as an input, not as a registration.

## Tickets

- **A9-1 (A9 -> A6/A8, main agent): resolved by option (a), with an end-to-end test.** §2 (contract) matched. §3
  (pass the parent's run-slice trajectories) is enforced by the donors guard and shown in gate (ii).
- **A9-2: request 1 resolved (`acceptance.runner`). Request 2 open (owner).** The owner needs to:
  - confirm the unit-blocked `_ordered` schedule, which differs from cal-1's uniform shuffle;
  - decide whether `rounds._order` should block the same way wherever `rounds.balance` applies.
  `rounds.balance` has no caller yet.
- **A9-3 (A9 -> A13, A1): driving recipe verified; MDE open.** Gate (ii) runs steps 1-4 exactly as the ticket lists
  them, with `acceptance.runner` as step 2's cell builder. The per-bench MDE constant is A1's/the owner's.
- **A6-1 (consumed by A9), A6-2 and A7-2 (consumed by A8): closed in B3.** Gate (ii) runs the placebo arms through the
  shell and the full path real shell -> cell -> judge -> v2 token -> item scores. The B1 open item 2 (stops looked up
  subclass-aware) is in `cells.run_cell` (`errors.stop_kind`).
- **A5-2 (drain check with two concurrent chains): open, not B3.** A5-1 and A3-1 are unchanged.

## Open

1. **Ticket A9-2 request 2 (owner):** the dispatch order of acceptance rounds and of training rounds where
   `rounds.balance` applies.
2. **Ticket A9-3 (A1/owner):** register the per-bench MDE, or name the SE that `stats_ext.mde` is given. Until then,
   `decision.mde_registered` is whatever the caller passes (None by default).
3. **A13, `workers(package, item)` factory.** `prepare` calls it with two kinds of item:
   - acceptance items, as raw task ids (`router.plan`, `placebo.real_lengths`);
   - donor items, as run-slice keys `<bench>/<task_id>`. Run-slice cells come from `rounds.run_round`, whose items are
     `rounds.key`, so a trajectory's `task_id` has that form.
   The factory must resolve both. On SpreadsheetBench it mounts that item's public workbook.
4. **A13, the acceptance unit.** It must:
   - register A (and the probe) before `prepare`;
   - pass `acceptance.round_packages(candidate, parent, step=sealed["step"], twins=sealed["plan"]["twins"])` and the
     `tasks` of A*, G_acc and the probe to `acceptance.runner`;
   - call `registry.decide` for A* and the probe after `acceptance.write`.
   On a redo, `donors.verify(sealed["corpus"], trajectories)` must pass first.
5. **Ticket A5-2:** call `drain_check` only where no other route-B unit runs, until A5-2 is decided.
