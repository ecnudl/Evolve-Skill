# C7c: S-E6, S4 (mini-step, drill, operator recovery), C7b2-3, C6b-1 leftover. S3 is NOT built.

Agent C7c, 2026-10-22. Protocol fivebench-execskill-v1, route B. Build tree `/data/execskill-dev` (= the Mac mount
`/Users/dulin/remote/dl`). Zero model calls, zero network, no docker run, no git write.

## Status

| Item | State |
|---|---|
| 1. C7b2-3 (FakeNative.precheck `tag=`/`docker=`, smoke.py wrapper dropped) + C6b-1 leftover (describer imports `DEFAULT_TARGET`) | done, tested |
| 2. S-E6 (C7b2-2): registered maximum-schedule cell counts + recompute test; `run_stage(..., "SE6")` | done, tested |
| 3. S4 (C7b2-1): smoke mode of `step.run_step`; `run_stage(..., "S4")` with the FaultSwitch drill; `write_recovery` + `smoke-recovery` CLI handler; redo | done, tested |
| 4. S3 (`smoke_roles.py`, `run_stage(..., "S3")`) | **missing**: out of time (see the last section) |
| 5. fake mode | done for S2, SN1, S4 (pause, drill, redo) and SE6. Not for S3. `smoke.summary` reads every stage and reports S3 `missing`, so it cannot pass yet |

## Files (C7c's edits only)

- `skillopt/execskill/protocol.py`:
  - `MAX_SCHEDULE_CELLS`: per step bench, step kind and cell bench, (card cells, procedure cells) at the registered
    maximum schedule (calc T4 rows; they give calc T6's caps).
  - `TEST_READ_CELLS`: per pilot and bench (calc T5 maximum rows).
  - `S4_DRILL_CALL = 50`.
- `skillopt/execskill/describer.py`: imports `DEFAULT_TARGET` from protocol; its local definition is dropped.
- `skillopt/execskill/step.py`: `SmokeStep` and `run_step(..., smoke=)`, the S4 mini-step (below); `SMOKE_BENCH`,
  `SMOKE_UNITS`.
- `skillopt/execskill/smoke.py`:
  - `BUILT_STAGES = ("S2", "SN1", "SE6", "S4")`.
  - `_backends` sets `precheck.precheck = native.precheck` (C7b-2's wrapper is gone).
  - S-E6: `SE6_STAGES`, `measured_cells`, `_per_cell`, `_bounds`, `_scope_cells`, `se6_projection`.
  - S4: `S4_DIR`, `DRILL_HISTORY`, `SMOKE_LABEL`, `RECOVERY_FIELDS`, `_confirm`, `_paused`, `_s4`, `s4_judged`,
    `write_recovery`, `add_arguments`, `recovery_cli`.
- `tests/execskill_fakes_env.py`: `FakeNative.precheck(..., tag=None, docker=None)` records `tag`.
- `tests/execskill_fakes_docker.py`: `FakeDocker.run` answers `image inspect --format {{.Id}} <image>` with the
  pinned id, as `manifest.image_id` expects. The S4 mini-step runs the manifest check before every unit, in the
  rehearsal too.
- `tests/test_execskill_protocol.py`: `test_maximum_schedule_cells_are_the_calc_t4_t5_counts_and_give_the_t6_caps`.
  It recomputes the counts from the calc script's own `step_cost` / `test_read` (sha256-pinned), then checks the
  tokens against `STEPS["max"]` and `TRMAX`, and the caps against `STEP_CAPS` and `test_read_cap`.
- `tests/test_execskill_smoke_rehearsal.py`:
  - The fixture now runs S2, SN1, S4 (stopped by the drill), `write_recovery`, S4 again (the redo) and SE6.
  - New tests: `test_s4_pauses_on_the_drill_and_the_operator_recovery_redoes_the_round`,
    `test_the_drill_recovery_is_written_only_into_a_paused_s4_attempt` and
    `test_se6_projects_every_solver_scope_of_both_chains_at_the_maximum_schedule`.
  - The last test refuses S0, not S4.
- `tests/test_execskill_smoke.py`:
  - `test_se6_measures_card_and_procedure_cells_and_charges_a_stopped_cell`
  - `test_se6_projects_every_solver_scope_and_prices_a_redo_as_one_acceptance_block`
  - `test_smoke_recovery_writes_the_owner_format_only_into_a_paused_s4_attempt`
- `tests/test_execskill_step.py`: `test_the_s4_mini_step_is_the_smokes_searchqa_step_1_with_a_candidate_of_the_empty_parent`.
- Unchanged: `budgets.py`, `tests/test_execskill_budgets.py`, `tests/test_execskill_describer.py`,
  `tests/execskill_fakes.py` and `tests/execskill_fakes_research.py`.

## Public API

- `protocol.MAX_SCHEDULE_CELLS[step_bench][kind][cell_bench] -> (card, procedure)`; kind is run, examiner,
  selftest or accept.
- `protocol.TEST_READ_CELLS[pilot][bench] -> (card, procedure)`; pilot is default or recommended.
- `protocol.S4_DRILL_CALL`: the drill's sandbox call number. It is an implementation-time registration.
- `step.SmokeStep(items, candidate, drill=None)`.
- `step.run_step(setting, "smoke", "searchqa", 1, parent, *, services, chain_root, smoke=SmokeStep)`.
  - It refuses (ValueError, before anything runs) any other chain, bench or k, a non-empty parent, or a candidate
    whose `parent_sha256` is not the parent's.
  - It runs only `run -> accept -> freeze`. Each unit is verified first with `setting.extra["verify"]`, which is
    `manifest.verify_unit`.
  - Solver: `budgets.solver_scopes("smoke", None, None, "smoke")` = (overall, smoke:solver), chain D's model,
    `ledger_bound(SMOKE_SOLVER, "searchqa", branch, longest)`.
  - Roles: `budgets.glm_scopes("smoke", role, None, None)`; S4 makes no role call.
  - Every registration has purpose "smoke" (the smoke namespace).
- `smoke.run_stage(spec, manifest_path, stage, *, fake=False, env_path=None, roles_repo=None)` for stage SE6 or S4.
  - SE6 needs no credential and makes no call.
  - S4 keeps C7b-2's money guards: `env_path` and `roles_repo` are named explicitly and must be the manifest's, the
    code map and image are verified, and the first single reply is confirmed (`_confirm`, its own unit) before the
    mini-step.
  - A pause returns `{"stage", "complete": False, "stopped", "reason", "unit", "paused": [attempt dirs]}`. It is
    kept, not judged.
- `smoke.se6_projection(spec, m)`: the judged S-E6 result, built with `se6_cost`.
- `smoke.measured_cells(cells)`.
- `smoke.s4_judged(chain_root, step_record, registry, items)`: the S4 result, built with `s4_ministep`.
- `smoke.write_recovery(spec, attempt, *, decision, date=None)`.
  - Writes the owner format exactly, `{"by": "owner", "date", "decision": "smoke drill (registration §10 S4): <text>"}`.
  - Writes once, and only into a paused, incomplete attempt of a mini-step unit (under
    `<smoke root>/units/S4/s1-searchqa`, never a confirmation unit).
  - Never called by `run_stage`.
- `smoke.add_arguments(subparsers)` adds the `smoke-recovery` subcommand (`--spec`, `--attempt`, `--decision`).
  `smoke.recovery_cli(args)` handles it. The wiring is in ticket C7c-1.

## S-E6 as built (§9.3, §10)

1. Inputs:
   - the cell records of every attempt of the recorded S2, SN1 and S4 units (`<root>/units/<stage>/**/attempt-*/cells/*.json`);
   - the smoke ledger `<root>/shared/ledger`, which must have no open reservation.
2. Per bench and arm, and per bench and class, it measures tokens per cell: prompt + completion of every send, over
   the cells with a verdict. The class is card (no procedure enabled) or procedure.
3. Ratio = `smoke:solver` settled / the reported tokens of ALL cells. A stopped cell counts too, because it was
   charged. The ratio must be <= 1.5.
4. For every solver scope of both chains (`budgets.chain_caps("G")` and `("D")`), it projects:
   needed = Σ (card cells x card tokens + procedure cells x procedure tokens) x ratio + R.
   - The cell counts are the registered maximum schedule.
   - R = 4 x (the largest measured request bytes of the scope's benches + 512 + B) (`coevo5.ledger.reservation`).
   - B is chain D's registered ledger bound (from the manifest's branch) or chain G's 65,536.
   - The scopes cover each step kind and its attempt-2/3 sub-scopes (an acceptance redo = ONE block, §9.3), the test
     read, the redo reserve and the solver total. For the last two it takes the dearest acceptance block.
5. Judged with `se6_cost`: any projection over its cap fails, which means a v1.1 re-registration before the pilot.
   `overall`, `<chain>:glm` and the role scopes hold no solver cells; they are listed under `not_projected`.
6. The record also carries `per_arm`, `per_class`, `per_cell`, `request_bytes`, `bounds`, `reservations`, `inputs`,
   and `anchors` (the card per-cell vs `CELL_ANCHORS`, flagged above `NOISE_REREGISTER` x high).

## S4 as built (§10)

1. The 60 S4 SearchQA items (`_slice("S4", "searchqa")`) are cut: run 20, accept 40 (`protocol.S4_SLICES`).
2. `<smoke root>/units/S4` is the mini-step's chain root.
3. First, one confirmation cell: the card arm on the first S4 item, alone, in `units/S4/confirm-<n>`, one per process
   run.
4. Then `step.run_step` in smoke mode:
   - candidate S' = the registrar's fixture package X, re-parented on the smoke's empty parent `smoke/s0`;
   - consumption goes to the drill registry `units/S4/history` (smoke namespace, purpose smoke).
5. The drill: `smoke.FaultSwitch(spec, accept unit root, fail_at=50)` wraps the acceptance cells' workers on the accept
   unit's FIRST attempt only, and raises `SandboxUnavailable` at the 50th sandbox call. The cell stops with kind
   sandbox, the unit pauses and the stopped report lists the paused attempt.
6. The operator writes `recovery.json` (`smoke-recovery`). The same `run_stage(..., "S4")` call then redoes the
   accept unit in attempt-2 on the same `sealed.json` and the same registrations, and freezes.
7. `s4_judged` rows:
   - `unit`: run, accept and freeze complete, with hashes as in `step.json`;
   - `consumption`: run items decided by the run unit; A* decided (accept/reject) or released (`routed_not_dispatched`)
     by the accept unit; each item registered exactly once;
   - `sealing`: the decision names `sealed.json`, the step's `decision_sha256` matches, and `acceptance.reproduce`
     passes on the last attempt's cells;
   - `redo`: exactly two attempts, the first paused with kind sandbox and holding a smoke-labelled owner recovery,
     the second the completed one.
8. Rehearsal result: A* = 40, 37 twins, decision reject (J1, J2) on the fakes, 216 cells, all four rows true.

## Frozen code checked (local mirror, commit 010d453)

- `skillopt/coevo5/budget.py:283-314` `Budget.reserve`: it admits only if settled + open + amount <= cap in every scope,
  else it waits or raises BudgetStop. S-E6 adds one full next reservation R per scope for this reason.
- `skillopt/coevo5/budget.py:344-351` `snapshot()`: per scope {cap, settled, open}. S-E6 reads `smoke:solver` from it.
- `skillopt/coevo5/ledger.py:30-36`: `attempt_bound` = size + 512 + max_tokens, and `reservation` = 4 x that
  (`coevo5/protocol.py:278-279`: CLIENT_ATTEMPTS 4, RESERVATION_OVERHEAD 512).
- `skillopt/coevo5/ledger.py:51-75` `settle`: the last attempt is charged its reported usage, earlier non-refused
  attempts the full bound. This is why the ratio can exceed 1.
- `skillopt/coevo5/evaluation.py:44` (`RECOVERY_FIELDS`), `:162-170` `attempts`, `:173-178` `recovered` (the owner
  format), `:181-187` `_next_attempt` (no new attempt without it). `write_recovery` writes exactly this format.
- `skillopt/coevo5/cells.py:237-258` `run_parallel`: after the drill error no further job starts and the running ones
  finish, so attempt-1 keeps the cells it finished.

## Throwaway in-image LiveMath checker run

Not run: S3 is not built. C7c made no docker call and no model call.

## Deviations (with reasons)

1. **Own drill registry `<smoke root>/units/S4/history`.**
   - The 280 SearchQA smoke items are already held in the real history root by `smoke/items` (purpose smoke,
     `s0.smoke_items`), and the smoke namespace admits only purpose smoke.
   - So the mini-step's registrations (run/accept, both purpose smoke) go to a registry of its own, where the
     registry behaviour (register, dispatch, release, decide, redo reuse) is exercised and judged. The history root
     is untouched.
2. **The candidate is fixture package X, and only run → accept → freeze run.**
   - SearchQA has no generation (§7.2). The method roles are S3's, so S4 makes zero GLM calls.
   - X is re-parented (`parent_sha256` = the smoke's empty parent), because the donor corpus requires it.
   - The sealed, decision and donor-corpus records carry X's evidence `engineering_fixture`; the unit, step and stage
     records carry `smoke`.
3. **A redo re-dispatches the WHOLE round,** as `acceptance.dispatch` does today. §9.3 says a pause redoes one block,
   and S-E6 prices attempt-N as one block, as registered. See ticket C7c-2: at the maximum schedule a whole-round
   OfficeQA redo would not fit its attempt sub-scope.
4. **One confirmation unit per process run** (`units/S4/confirm-<n>`), so every process's first reply is confirmed
   alone before anything concurrent. C7b-2 confirms inside the first unit; S4's units belong to `step.run_step`.
   - A paused confirmation unit is never redone (the next run confirms in a new unit), so the stopped report's
     `paused` lists only the mini-step's attempts, and `write_recovery` refuses a confirmation unit.
   - A not-confirmed first reply stops S4 with `first_call_not_confirmed` and `paused: []`. Check it, then re-run.
5. **Drill placement.**
   - The drill fires on the accept unit's first attempt only, at the 50th acceptance sandbox call. A new process's
     redo is not drilled again.
   - With X on SearchQA, A* is all 40 items (fx-print applies to every item), so the drill fires.
   - A too-small A* is recorded, not crashed (`astar_small` true, `redo` row false, so S4 fails honestly: the drill
     could not be exercised).
6. **S-E6 classes cells as card or procedure,** because the maximum schedule counts those two classes (calc PO
   factors). A bench without a measured procedure cell is priced at `PROCEDURE_ARM_FACTOR` high (1.6) x card and
   flagged `procedure_assumed`.
7. **S-E6 prices chain G at the elucid per-cell tokens** with G's own B = 65,536 in R. This is a placeholder; per
   §9.3, chain G gets its own check after its first run unit.
8. **The calc recompute test reads `docs/handoff/execskill-calc-20261021.py`.** It looks beside the tree, else at
   `protocol.BUILD_TREE`, with the sha256 pinned, and skips if absent. The S0 snapshot copies only
   skillopt/scripts/tests.
9. **The rehearsal pins the dev tree's code map at fixture time,** and the S4 mini-step verifies it before every unit.
   A concurrent edit under skillopt/ or scripts/ during the ~2-minute rehearsal makes S4 stop with "Files differ from
   the launch manifest". That is expected; re-run.

## Tickets

- New:
  - `tickets/C7c-1.md` (C7b-1 / integrator): `smoke_run` prints `result["passed"]`. That key exists neither in the
    stage record (it is `result["result"]["passed"]`) nor in a stopped report, so it raises KeyError on every stage,
    and S4 always stops first. The ticket also gives the `smoke-recovery` wiring lines (`smoke.add_arguments(sub)`,
    `"smoke-recovery": smoke.recovery_cli`, a usage line).
  - `tickets/C7c-2.md` (integrator, owner decision #15): an acceptance redo re-runs all blocks, but §9.3 says one block.
- Closed: C7b2-1 (S4), C7b2-2 (S-E6), C7b2-3 (FakeNative precheck), and the C6b-1 leftover (`DEFAULT_TARGET`).

## pytest (dl, `PYTHONDONTWRITEBYTECODE=1 /root/continual-alf-prep-20260928/env/bin/python -B -m pytest -q -p no:cacheprovider`)

- `tests/test_execskill_protocol.py tests/test_execskill_describer.py` (after items 1-2): 23 passed.
- `tests/test_execskill_smoke_rehearsal.py`: 8 passed in 106.09s (S2, SN1, S4 with drill, recovery and redo, SE6).
- `tests/test_execskill_smoke.py tests/test_execskill_protocol.py tests/test_execskill_describer.py
  tests/test_execskill_budgets.py` and the new step test: 52 passed in 6.07s.
- **Whole route-B suite** (`tests/test_execskill_*.py`, log `/tmp/c7c-suite.log` on dl): **1020 passed in 659.20s
  (0:10:59)**, 0 failed. It ran before C7c's last small patch: line lengths, the stopped report's `paused` list
  limited to the mini-step's units, and the recovery guard to match.
- After that patch: `tests/test_execskill_smoke.py tests/test_execskill_smoke_rehearsal.py tests/test_execskill_step.py
  tests/test_execskill_protocol.py tests/test_execskill_describer.py tests/test_execskill_budgets.py`: **67 passed in
  153.42s**.
- The task's exact command also names `tests/test_execskill_smoke_roles.py`. That file does not exist (S3 is
  missing), so the command was run without it.

## Operator invocations (real; dl, from the verified snapshot, after S0/S1 pass)

Order: S2 → SN1 → S4 (pauses on the drill) → smoke-recovery → S4 again (the redo; records S4) → SE6 → S3 (once built)
→ smoke-summary. SE6 needs the S2, SN1 and S4 records and a smoke ledger with nothing open.

Until ticket C7c-1 is fixed, `smoke-run` raises KeyError after the stage returns: the stage record is written anyway,
but the S4 stopped report is not printed. Use the Python form. In tmux `execskill-smoke`, background:

    cd /data/execskill-20261021-source && unset OPENAI_API_KEY OPENAI_BASE_URL && export PYTHONDONTWRITEBYTECODE=1 &&
    /root/continual-alf-prep-20260928/env/bin/python -B -c 'import json; from skillopt.execskill import smoke;
    print(json.dumps(smoke.run_stage("/data/execskill-20261021-pre/smoke/smoke.json", "<smoke manifest>", "S4",
    env_path="/root/.config/weak-solver/elucid.env", roles_repo="<clients.solver.G.env_path>"), default=str))'

The first S4 call prints the stopped report, with `"stopped": "sandbox"` and
`"paused": ["<smoke root>/units/S4/s1-searchqa/accept/attempt-1"]`. The operator's drill (zero calls):

    /root/continual-alf-prep-20260928/env/bin/python -B scripts/run_execskill.py smoke-recovery \
      --spec /data/execskill-20261021-pre/smoke/smoke.json \
      --attempt <smoke root>/units/S4/s1-searchqa/accept/attempt-1 \
      --decision "redo the accept round with the same sealed inputs"

Python form, until the subcommand is wired: `smoke.write_recovery(smoke.load(SPEC), ATTEMPT, decision=TEXT)`.
Then repeat the S4 call: it redoes the round and records S4. Then S-E6 (zero calls, no credential):

    /root/continual-alf-prep-20260928/env/bin/python -B -c 'import json; from skillopt.execskill import smoke;
    print(json.dumps(smoke.run_stage("/data/execskill-20261021-pre/smoke/smoke.json", "<smoke manifest>", "SE6"),
    default=str))'

Once C7c-1 is fixed, the CLI forms are:
- `scripts/run_execskill.py smoke-run --spec SPEC --manifest M --stage S4 --env-path /root/.config/weak-solver/elucid.env --roles-repo <clients.solver.G.env_path>`
- `scripts/run_execskill.py smoke-run --spec SPEC --manifest M --stage SE6`

A stopped report on another unit (the cap, connectivity, the first reply not confirmed) needs the owner's own
`recovery.json` in that attempt, by the existing `recover` subcommand. `smoke-recovery` writes only into S4 attempts.

## S3: exactly what is missing (next row)

- **Code:** `skillopt/execskill/smoke_roles.py` (new), `run_stage(..., "S3")`, and "S3" in `BUILT_STAGES`.
- **Calls, each GLM-5.3 through the frozen client on `smoke:glm` (S3 <= 0.5M):** use
  `budgets.glm_scopes("smoke", role, None, None)` with `setting.clients(ROLE_MODEL, None)` and
  `max_tokens_bound=ROLE_MAX_TOKENS`, as `step._Step.roles` does in smoke mode. The first single reply is confirmed
  before the rest. The pieces:
  - one engineer call (the C1-C9 flow);
  - one detector write and its hold-half validation;
  - one LiveMath-type generation, after ONE research request on the frozen sources (archive write-once, verbatim
    quote check, <= 8 calls, `protocol.GATEWAY`);
  - a registrar LiveMath truth checker that runs inside the pinned image (sympy is only there), applied to >= 5
    generated items;
  - one leakage adjudication;
  - one describer call.
- **Judge:** `smoke.s3_roles`.
- **Guards:** `roles_repo` must equal the manifest's G block path.
- **Tests and runs not done:**
  - the fakes (FakeGLM, FakeResearch, the in-image checker through FakeDocker);
  - `tests/test_execskill_smoke_roles.py`;
  - S3 in the rehearsal, so that `smoke.summary` can seal a passing smoke;
  - the throwaway in-image checker run.
