# PR-C61 progress (ticket C6-1: production SpreadsheetBench engines)
- 12:4x read: generators/sheet.py, generators/__init__.py, step.py Services, manifest.services_of, frozen sheet_numeric_adapter.qualified_engine, sheet_recalc_v7/v5 Recalculator, qualify.py (I1's engine_runtime/revalidate), slots.py, errors.py; found sheet.py private fields lack asset_sha256 and generated references lack answer caches (to verify in the real check)
- 12:45 DONE skillopt/execskill/engines.py (Recalculation, sheet_engines)
- 12:44 DONE real step 1: frozen v7 engine qualification from /data/execskill-dev into /tmp/pr-c61-q: qualified, 23/23 controls, 21 containers, 0 cleanup unconfirmed, 0 model calls, 80 s
- 12:46 DONE tests/test_execskill_engines.py: 10 passed in 1.21s (dl)
- 12:48 DONE real check (0 model calls): engine_runtime 0.5 s; first-use revalidation 0.5 s; recalc fx-sb-00/01/02 all available, cleanup confirmed, answer cells = fixture truth 1/1, 6/6, 1/1; generate with the production engine PAUSED configuration (native_scoring_input_error:ValueError: generated private lacks asset_sha256); with asset_sha256 the item is excluded reference_cache_mismatch (generated reference has no answer cache); with asset_sha256 + engine-refreshed reference: qualified 1/1
- 12:49 DONE cleanup: /tmp/pr-c61-* deleted, 0 containers left, no __pycache__ in the dev tree
- 12:55 DONE tickets PR-C61-1 (I1: services_of wiring + test change + LiveMath note) and PR-C61-2 (generators/sheet.py: asset_sha256 + reference caches, verified fix candidate)
- 12:57 DONE mutations M1-M8 (slot across revalidation, cleanup stop, caching, binding, environment stop, no slot, evidence, runtime copy): all killed (throwaway /tmp/pr-c61-mut, deleted)
