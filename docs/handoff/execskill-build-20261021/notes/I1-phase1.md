# I1 phase 1 (integrator, route B): C7b1-3, the pool export, C7c-1, the runbook merge

Agent I1, 2026-10-22, 12:32-13:05 (dl clock). Protocol fivebench-execskill-v1. Build tree `/data/execskill-dev`
(= the Mac mount `/Users/dulin/remote/dl`). **Zero model calls, no network, no git write.** The only docker use was
the zero-call engine identity and revalidation check (no container started). Throwaway dirs `/tmp/i1-engine` and
`/tmp/i1-pools` on dl were deleted. I did NOT run `replay_sheet_v6 qualify`: it starts recalculation containers, and it
is the main agent's step 2b after the commit and the snapshot. Progress log: `notes/I1-progress.md`.

## Status

| Item | State |
|---|---|
| 1. C7b1-3 (registrar option (a)): `engine_runtime`, `same_engine_sources`, S0 sheet row, CLI, runbook step 2b | done, tested, real zero-call checks (below) |
| 2. C7b1-2 / C6-3: `export-pools`, `smoke-items` on the export | done, tested, real throwaway export reproduces OPS1's digests |
| 3. C7c-1: `smoke-run` verdict or stopped report; `smoke-recovery` wired | done, tested |
| 4. Runbook merge (OPS1 inputs, S2 → SN1 → S4 → smoke-recovery → S4 → SE6 → S3) | done |
| 5. Tests and `--help` for every subcommand | done: 94 + 111 passed, 34/34 `--help` |

## Files changed (file:line as of 13:05)

- `skillopt/execskill/qualify.py`
  - :20-29 docstring paragraph on the recalculation engine; :33-37 imports (`hashlib`, `os`, `PurePosixPath`).
  - :48 `__all__` adds `SCORER`, `engine_runtime`, `revalidate`, `same_engine_sources`, `snapshot_root`.
  - :54-57 `SCORER`, `ENGINE_PROFILE`, `REPLACED`, `PACKAGE`; :64 `qualify()` now uses `SCORER`.
  - :151-243 `revalidate` (:152), `_engine_record` (:167), `engine_runtime` (:180), `snapshot_root` (:205),
    `_relative` (:218), `same_engine_sources` (:225).
- `skillopt/execskill/s0.py`
  - :31-41 docstring (the sheet row; the smoke items read the export).
  - :147-148 `Deps.engine_runtime`, `Deps.same_sources`; `Deps.qualify_fixtures` now takes `(tasks, root, runtime)`.
  - :569-590 `collect(..., engine_qualification=None)` with the real-path precondition at :586; :624 `sheet()` calls
    `sheet_row`.
  - :660-684 `sheet_row`; :686 `_sheet_import` requires side train and also returns `recalculation`;
    :698 `_qualify_fixtures(tasks, target, runtime)` with `qualify.SCORER`.
  - :751-790 `smoke_items`: `supply.load_pool` plus the 600 check (:762-764).
  - :793-840 `fake_deps` with `_fake_qualification` (:816), `_fake_sheet_import` (:822), `_fake_engine_runtime`
    (:827), `_fake_same_sources` (:834).
- `skillopt/execskill/supply.py`
  - :25-28 docstring bullet; :42 `from skillopt.coevo5 import data as frozen_data`.
  - :84-87 `REGISTERED_POOLS`, `SHEET_QUALIFIED`, `POOL_KIND`, `POOL_RECORD`.
  - :407-490 `export_pool` (:407), `_sha256` (:435), `write_pool_export` (:439), `pool_pins` (:463), `load_pool` (:470).
- `scripts/run_execskill.py`
  - :20-45 usage lines (`export-pools`, `sheet-runtime`, `smoke-recovery`, the `s0-collect` flags, the `smoke-run`
    exits, the `make-manifest` revalidation, `smoke-items`); :86 imports `chain`.
  - :385-399 `s0_collect`: `--engine-qualification` required unless `--fake`.
  - :402-412 `sheet_runtime`; :415-435 `export_pools`; :438-451 `smoke_run` (C7c-1); :460-477 `make_manifest`
    revalidation (:474-477).
  - :615-621 parsers `export-pools`, `sheet-runtime`; :642 `s0-collect --engine-qualification`;
    :653 `smoke.add_arguments(sub)`; :705-707 HANDLERS (`export-pools`, `sheet-runtime`, `smoke-recovery`).
- `tests/test_execskill_qualify.py`: helpers :145-182 (`IMAGE`, `SOURCES`, `identity`, `engine_record`,
  `v3_sheet_runtime`); new tests :184, :221, :238.
- `tests/test_execskill_s0.py`: helper `_searchqa_export` :280; updated :288; new :321, :358, :389, :428; helpers :343,
  :352.
- `tests/test_execskill_supply.py`: helper `_frozen_pool` :286; new :300, :342, :352.
- `tests/test_execskill_cli.py`: replaced :440 (`smoke_run`); new :474, :521, :548, :586, :624, :673; helper
  `_v3_manifest` :541.
- `docs/handoff/execskill-build-20261021/smoke-runbook.md`: rewritten (about 350 lines).
- `notes/I1-progress.md`, `notes/I1-phase1.md` (this note).

Not edited: `smoke.py`, `smoke_roles.py`, `acceptance.py`, `step.py`, `generators/*` (C7d, C7e), `manifest.py` (not
needed), every frozen file, the ticket files.

## Public API

- `qualify.SCORER` = `"qualified_lo_recalc_v7_v1"`; `qualify.REPLACED` = the three replaced recalculation fields.
- `qualify.revalidate(runtime) -> record_hash`. This is the frozen `sheet_numeric_adapter.qualified_engine` (offline,
  zero calls). It turns OSError, ValueError, KeyError or TypeError into `ValueError("The SpreadsheetBench engine
  qualification does not revalidate from this checkout (ticket C7b1-3): <type>: <message>")`.
- `qualify.engine_runtime(base_runtime, qualification_path, *, check=None) -> runtime` (a new dict).
  - Requires a v7-scorer base with a `recalculation` holding the three fields.
  - The record must be sealed, `status` qualified, `engine_profile` v7, `model_api_calls` 0, with non-empty
    `engine.sources`, and of the base's image and timeout.
  - Replaces only `qualification_path` (absolute), `qualification_sha256` (file sha256) and `qualification_hash`
    (the record's `record_hash`), then runs `check(runtime)`, by default `revalidate`.
- `qualify.snapshot_root(sources) -> PurePosixPath`: the directory that holds the last `skillopt` component of the
  sources' common path.
- `qualify.same_engine_sources(new_qualification_path, old_qualification_path)` returns `{"same", "fields":
  {"compared", "differing"}, "sources": {"new", "old", "equal", "differing"}, "roots": {"new", "old"}}`. It takes
  the two record paths, so both seals are verified.
- `s0.collect(..., engine_qualification=None)` and `s0.sheet_row(deps, *, source, sha256, base_runtime,
  engine_qualification, fixtures_dir, target)`. The row's evidence is `{"import": {version, summary}, "engine":
  {qualification_path, qualification_sha256, qualification_hash, same_sources_as_v3_training}, "fixtures": {items,
  qualified, excluded, all_qualified, record_sha256}}`.
- `supply.REGISTERED_POOLS` = SB 120, OQ 74, LM 283, SQA 600, ALF 57; `supply.SHEET_QUALIFIED` = 91.
- `supply.export_pool(pinned, bench, *, sheet=None) -> (items in supply.order, counts)`.
- `supply.write_pool_export(out, pools, *, source, evidence="smoke") -> sealed record` (`pools.json`, kind
  `pool-export`).
- `supply.pool_pins(record) -> {bench: {path, sha256}}`, the `data.pools` block.
- `supply.load_pool(path, bench) -> items`, verified against `pools.json` beside the file (recorded path, sha256, count).
- CLI:
  - `export-pools --manifest V3 --out NEWDIR`.
  - `sheet-runtime --manifest V3 --engine-qualification Q --out NEWFILE`.
  - `s0-collect ... --engine-qualification Q` (required unless `--fake`).
  - `smoke-recovery --spec S --attempt A --decision TEXT`.
  - `smoke-run` prints `{"stage", "passed"}` and exits 0 or 3. On a stopped report it prints `stage`, `stopped`,
    `reason`, `unit` and `paused`, and exits `chain.EXIT_PAUSED` (3).
  - `make-manifest` revalidates a v7 `runtime.spreadsheetbench` before writing anything.

## Real zero-call checks

1. `same_engine_sources`, the dev tree's live v7 identity against q23-f: same. 13 of 13 non-source fields are equal
   and 7 of 7 sources are equal. Roots: `/data/execskill-dev` and `/data/coevo5-20261019-v3-source-f`.
2. `engine_runtime(<v3 block>, q23-f, check=no-op)` equals v3's `runtime.spreadsheetbench` exactly.
3. The default check from the dev tree refuses q23-f with `... does not revalidate from this checkout (ticket C7b1-3):
   ValueError: Engine/source/image changed`. This is expected, because q23-f is bound to v3's checkout. The real
   `sheet-runtime` therefore cannot run before step 2b.
4. `export-pools` from the v3 manifest into `/tmp/i1-pools` exited 0 in about 1 min. The results:
   - SearchQA 600 (400/200). The digests equal OPS1's: sorted ids `901fb49e219da901`, supply-order ids
     `332df1bffc67468e`, items `120f123facc30534`.
   - SearchQA slices: the smoke slice is 280 = 198 train + 82 val (`7033d48d685c4cba`); the run slice is 300
     (`50ce48330655cf2d`).
   - SB 120 → 91 (58/33) → run 31 + accept 60.
   - OQ 74 → 24/50.
   - LM 283 → run 119, accept 100, probe 64.
   - ALF 57 (see I1-1).

## Deviations and interpretations

1. **The SpreadsheetBench pool is exported as the 91 qualified items.** The pool count of 120 is checked first, and
   the training qualification's `task_hashes` must equal `digest(item)` of exactly those items. Three sources agree on
   this: C6-3 ("must already be the qualified one"), v3's manifest (`data.qualified`, `coevo5/manifest.py:129`) and the
   registered slices (31 + 60). The record keeps `pool` 120, `parts` 80/40, `items` 91 and `written_parts` 58/33.
2. **`smoke-items` reads only an exported file.** It must match the `pools.json` beside it (recorded absolute path and
   sha256) and hold exactly 600 items. A plain list, 580 items or a tampered file are refused. The export is bound to
   its location. `manifest._items` checks only the sha256, so the pilot pins are unaffected.
3. **ALFWorld export items gain `room` and `task_type`** (C6-3: "ALFWorld items with `room`"), via
   `supply.task_folder`.
4. **`s0.collect` fails before any row on the real path** if `engine_qualification`, `manifest_path`, `sheet_source` or
   `sheet_sha256` is missing. S0 is collected once per root, so a failure late in the run would waste the root.
5. **Sealed reads.** `export-pools`, `sheet-runtime` and `make-manifest` read the v3 manifest with `sealed=True`. S0's
   existing read is unchanged.
6. **`engine_runtime` also checks the engine's image and timeout.** The record's engine `image_id` and
   `timeout_seconds` must equal the base block's ("keeping image and timeout"), so a qualification of another image
   cannot slip in.
7. **`make-manifest` revalidates only a `runtime.spreadsheetbench` with the v7 scorer** (as asked). Pins without such a
   block are left to the existing checks.
8. **The per-call slot size is deferred** (C7b1-2 slot part), and documented as a safe failure (runbook §0).

## Tickets

- **Closed:**
  - C7b1-3: the implementation side. The main agent still runs the qualification (runbook step 2b).
  - C7b1-2: the pool part.
  - C6-3: the exporter part.
  - C7c-1.
- **Documented, unchanged:**
  - C7b1-1: S0 fails its measurements row if the derived limits differ from the start limits. They were equal on 10/22.
  - C7b1-2, slot part: deferred, with a safe failure.
- **Still open, not mine:**
  - C7c-2: the one-block redo (C7e).
  - S3 (C7d).
  - `--control-cells` and `--noise-anchor` (registrar; `smoke-inputs.md` §6).
- **Opened, I1-1 (registrar or main agent; recommended pilot only).** The v3 ALFWorld pool (57 games, as the task
  registered it) cannot hold the registered ALFWorld slices: `supply.slices` raises "Too few items for the smoke slice"
  (smoke 12, run 60, accept 150, select 200). The step cuts `setting.pools["alfworld"]` with these sizes
  (`step.py:278`). The default pilot (SB → OQ) does not need ALFWorld, but the recommended pilot (SB → ALF) would need
  a `data.pools` entry built from the fresh supply (`$HIST/supply/alfworld-xs.json`, items with rooms) as a JSON list.
  No command writes that. The export's `alfworld.json` remains the v3 pool.

## Tests (dl, `PYTHONDONTWRITEBYTECODE=1 $PY -B -m pytest -q -p no:cacheprovider`)

| What | Result |
|---|---|
| My test files: qualify, s0, supply, cli, runcli, manifest | **94 passed, 0 failed** (21 s) |
| Dependents of the changed modules: canaries, engines, exclusion, fixtures, integration_b1, integration_b2, registry, protocol, solver | 111 passed (35 s) |
| `--help` for every subcommand, from the real script (cwd `/tmp`) | 34/34 exit 0 with `usage:` |

- New or changed by I1: qualify 3 new; s0 4 new and 1 updated; supply 3 new; cli 6 new and 1 replaced.
- Not run: the whole suite and `tests/test_execskill_smoke_rehearsal.py` (phase 2). C7d and C7e are editing
  `smoke.py` and `step.py` concurrently, and the rehearsal stops on a concurrent code-map change (C7c deviation 9).
- Lines longer than 120 characters: only pre-existing ones remain (`run_execskill.py:208`, `test_execskill_s0.py:122`,
  `test_execskill_cli.py:103,105`).

## What phase 2 must still do

1. After C7d (S3) and C7e (the one-block redo) finish, copy the dev tree to a fresh throwaway `/tmp/i1-*` (no `.env`,
   `.git` or `__pycache__`). Run every `tests/test_execskill_*.py` there, including C7d's new
   `tests/test_execskill_smoke_roles.py`. C7c's last full run took about 11 min and gave 1020 passed.
2. Run the full CLI fake rehearsal, S0 → S4 → summary, in a throwaway root through `scripts/run_execskill.py` only:
   - make-fixtures;
   - a synthetic 600-item SearchQA export via `supply.write_pool_export` (400 train + 200 val, as in
     `tests/test_execskill_s0.py::_searchqa_export`), because `smoke-items` now refuses a plain list;
   - smoke-items, sandbox-selftest, `s0-collect --fake` (no `--engine-qualification`), smoke-make, smoke S0 and S1,
     make-manifest;
   - `smoke-run` S2 and SN1, then S4 (expect exit 3 with `paused`), `smoke-recovery`, S4 again, SE6, S3;
   - smoke-summary, which must pass.
3. Fix the integration problems this finds in my files, and open tickets for files I do not own.
4. Update runbook §0 and §6: the S3 line from C7d's note (flags, judge), and the C7c-2 line from C7e's result.
5. For the main agent, not I1. After the commit and the snapshot, from `$SRC`:
   - step 2b's `replay_sheet_v6 qualify` into `/data/execskill-20261021-sheet-q23`, then `sheet-runtime`;
   - `export-pools --out $PRE/pools` (expect the digests above);
   - `s0-collect --engine-qualification $Q23/qualification.json`.

   The registrar must still decide `--control-cells` and `--noise-anchor`, and I1-1 if the recommended pilot is taken.
