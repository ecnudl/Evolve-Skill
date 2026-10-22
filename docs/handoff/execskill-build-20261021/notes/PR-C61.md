# PR-C61: production SpreadsheetBench engines for `step.Services` (ticket C6-1; protocol fivebench-execskill-v1, route B)

PR-C61, 2026-10-22 12:4x-12:5x. Build tree `/data/execskill-dev` (mount `/Users/dulin/remote/dl`). Zero model calls,
zero network, no git command, no credential or test-pool file read, no frozen file edited. Binding sources: ticket
C6-1, registrar decisions 2026-10-22 (C7b1-3 addendum 12:0x; 13:0x addendum: the pilot-readiness row "C6-1 production
engines in Services", built now and reviewed in the same single Codex round), registration §7.2 "SpreadsheetBench 族"
([SF F24]), §4.4 (P4 row), §10 S0; plan §1 generators row, §4 "Slots and lock order", §5.

## Files changed
- NEW `skillopt/execskill/engines.py` (115 lines):
  - :1-39 module docstring (engine parts, native slot rule, receipt rules, citations);
  - :58 `REVALIDATION_ERRORS` (the four classes the frozen `sheet_numeric_adapter.readiness` catches, :82);
  - :61-103 `class Recalculation` (`engine()` :73, `__call__` :88);
  - :106-115 `sheet_engines`.
- NEW `tests/test_execskill_engines.py` (279 lines, 10 tests; `FakeRecalculator` :41, `_engine_of` :81).
- NEW tickets `tickets/PR-C61-1.md` (I1: `services_of` wiring), `tickets/PR-C61-2.md` (owner of `generators/sheet.py`).
- Notes: this file and `notes/PR-C61-progress.md`.
- Not touched: `generators/sheet.py`, `manifest.py`, `step.py`, `qualify.py` (read only; I1's `engine_runtime` used in the real check).

## Public API
- `engines.sheet_engines(runtime, *, native, evidence, engine_of=None) -> generators.sheet.Engine`
  - `recalc` = `Recalculation(runtime copy, native)`; `qualify` = `functools.partial(qualify.qualify, evidence=evidence)`;
    `runtime` = a deep copy of `runtime`; `native` = the pool.
  - Refuses an unknown evidence label and a `native` without `hold()`. Revalidates nothing.
- `engines.Recalculation(runtime, native, *, engine_of=None)`: `Engine.recalc`.
  - `engine()`: the frozen v7 `Recalculator` from `engine_of(runtime)` (default: the frozen
    `sheet_numeric_adapter.qualified_engine`). It runs once and is kept with the qualified identity, under a lock.
    A refusal (OSError/ValueError/KeyError/TypeError) is re-raised as ValueError naming it. A qualified record whose
    `engine` is not the engine's identity is refused.
  - `__call__(path) -> receipt`: the input's sha256 is taken first; then ONE `native.hold()` around `engine.run(path)`
    only. After the slot is released:
    - `cleanup_confirmed` not True → `CleanupUnconfirmed`;
    - a receipt not bound to {input sha256, qualified identity, `model_api_calls` 0} → ValueError;
    - a reason in `coevo5.outcomes.SCORER_ENVIRONMENT` → `SandboxUnavailable`;
    - otherwise the frozen receipt is returned unchanged (an unavailable one becomes `sheet`'s `recalc_failed` drop).

## Real zero-call check on dl (throwaway `/tmp/pr-c61-*`, all deleted; 0 containers left; no `__pycache__` written)
1. The frozen v7 engine qualification, v3's command (`/data/coevo5-20261019-v3-ops/f/prep-v3f.sh:11`) from the dev
   tree: `PYTHONPATH=/data/execskill-dev python -B -m scripts.replay_sheet_v6 qualify --output /tmp/pr-c61-q --image
   sha256:f7f6…d790 --legacy-qualification …/q17/qualification.json --comparison-fixture-qualification
   …/continual-unknown-sheet-v6-20261001-q/qualification.json --native-lock …/native.lock --engine-version v7`.
   Result: `qualified`, profile v7, 23/23 controls qualified, 23 workbooks closed, 21 containers, cleanup unconfirmed 0,
   model calls 0, 80 s. The identity's sources are keyed by `/data/execskill-dev/...`.
2. The runtime: I1's `qualify.engine_runtime(v3 runtime.spreadsheetbench, /tmp/pr-c61-q/qualification.json)`. Only
   `qualification_{hash,path,sha256}` were replaced, every other field equal; it revalidated in 0.5 s. The engine's
   first-use revalidation also took 0.5 s.
3. `make-fixtures --out /tmp/pr-c61-fx` (20/20/20), then `engine.recalc` on three reference workbooks:

   | fixture | kind | status | reason | cleanup | calls | literals verified | answer cells = fixture truth | s |
   |---|---|---|---|---|---|---|---|---|
   | fx-spreadsheetbench-00 | sum | available | independently_recalculated | true | 0 | 10 | 1/1 | 3.8 |
   | fx-spreadsheetbench-01 | row_product | available | independently_recalculated | true | 0 | 12 | 6/6 | 3.0 |
   | fx-spreadsheetbench-02 | average | available | independently_recalculated | true | 0 | 14 | 1/1 | 3.7 |

   The native slot was free after each call.
4. Beyond the three receipts, one `generators.generate(sheet.FAMILY, ...)` ran with the production engines on
   fx-spreadsheetbench-00 (edit `B3 = ROUND(B2*3+1,0)`):
   - It ended in `Pause("configuration", "native_scoring_input_error:ValueError")` at the first engine-qualification
     scoring. The cause: the generated item's private fields carry no `asset_sha256`.
   - The same task with `asset_sha256`: qualified 0, excluded `reference_cache_mismatch`. The generated reference had
     no answer cache.
   - With `asset_sha256` and the reference re-recalculated by the engine: qualified 1/1, 2 scorings, 0 calls.
   - Both defects are in ticket PR-C61-2.

## Readings and deviations (for the single Codex round)
1. **Revalidation at the first recalculation, not at construction.**
   - `services_of` runs in every step-unit child and in `chain.run_manifest`, also for QA steps.
   - The manifest tests build Services from `runtime = {b: {} ...}`.
   - `make-manifest` and S0 already revalidate the same runtime (C7b1-3).
   - Cost is not the reason (0.5 s measured). A stale runtime pauses the generate unit as "configuration" at the
     first recalculation.
2. **Two receipt outcomes are stops, not `recalc_failed` drops**:
   - an unconfirmed container removal → `CleanupUnconfirmed`, as `coevo5.qualify._check` stops on it;
   - the three `SCORER_ENVIRONMENT` reasons (no Linux docker, image or daemon unavailable, unsafe image) →
     `SandboxUnavailable`, P4 "镜像缺失、docker 起不来".
   - Reason: an infrastructure failure must not turn every parameter set into a generator drop. Otherwise a "none
     kept" generation result would be silently recorded as a method outcome.
   - The frozen per-item qualification (copied in `qualify.qualify`) does not stop on SCORER_ENVIRONMENT; it excludes
     the item. With docker down, the recalc stops first.
   - Timeouts, execution errors, screen refusals and unverified read views stay drops.
3. **The receipt binding uses the identity captured at revalidation.** This is stricter than the frozen per-call
   identity: a scorer source edited mid-run is refused.
4. **The native slot is held around `run` only.**
   - `spreadsheet-native` is the last lock level, so a model call under it is refused by `assert_order`. This is
     tested: a model slot and a second native slot inside the run raise `slot_lock_order`.
   - A thread that holds a model slot may still recalculate. This is allowed by the registered order and tested.
5. **The real check differs from v3's run in two ways:**
   - it used `-B`/`PYTHONDONTWRITEBYTECODE=1` (v3's prep ran without `-B`);
   - it ran from an empty cwd instead of `cd $S`.
   - Reason: no `.pyc` in the shared dev tree. The identity comes from the PYTHONPATH module paths, so it is the same.
   - Step 4 above went beyond "receipts status and counts only". That is how PR-C61-2 was found and verified (all
     zero-call).

## Tickets
- PR-C61-1 → I1: the exact `services_of` change.
  - Import `engines`.
  - `engine=engines.sheet_engines(setting.runtime["spreadsheetbench"], native=setting.slots[slots.NATIVE],
    evidence=m["evidence"])`.
  - The docstring line.
  - The `test_a13_1_services_of...` assertion change (`services.engine is None` → a `sheet.Engine` bound to the native
    pool, the runtime and the evidence).
  - The LiveMath note: C7d's adapter was not in `generators/livemath.py` when I finished (file unchanged since 02:42).
    When it lands, it goes in the same return statement. It must not start a container while the Services are built,
    and it must carry the unit tag like `workers`.
- PR-C61-2 → registrar / main agent (owner of `generators/sheet.py`). This blocks pilot step 1 even after PR-C61-1:
  - (1) `private_fields` lacks `asset_sha256`. Every scoring of a generated SpreadsheetBench item pauses as
    "configuration" (`sheet_numeric_adapter.py:93-94`, `backends.py:566`, `coevo5/qualify.py:63-64`).
  - (2) openpyxl's save drops the reference's formula caches. Every item fails `engine_qualification_failed`
    (`reference_cache_mismatch`; `sheet_recalc.py:610-612`, `spreadsheet_compat.py:246-260`).
  - Verified fix candidate: `asset_sha256` for both written files, and the generated reference = the engine's
    recalculation of the generated `answer.xlsx`.

## Tests (dl, prescribed interpreter, own file only)
- `tests/test_execskill_engines.py`: 10 passed in 0.98s (final), 1.21s (first run).
- Break-the-code mutations on a throwaway copy (`/tmp/pr-c61-mut`, deleted): 8/8 killed. The mutations were: slot held
  across the revalidation; no cleanup stop; revalidation on every call; no binding check; no environment stop; no
  native slot; wrong evidence bound; runtime not copied.
- Not run: the whole suite and `tests/test_execskill_smoke_rehearsal.py` (its code map now sees two new files), both
  left to the integrator.

## Not done (exact)
- The engines are not wired into `Services` (I1, PR-C61-1). The LiveMath checker is not provided (C7d).
- The `generators/sheet.py` defects are not fixed (PR-C61-2). Until they are, no generated SpreadsheetBench item can be
  kept.
- No suite test runs the real frozen `qualified_engine` against a real qualification or a real container. The real
  check was manual and throwaway.
- The pilot's engine qualification must still be made from the final snapshot into
  `/data/execskill-20261021-sheet-q23` (main agent, after the commit; C7b1-3). The `/tmp/pr-c61-q` record was
  throwaway and is deleted.
