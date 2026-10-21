# Notes (2026-10-11, afternoon): what it takes to run learning v11 on SpreadsheetBench and ALFWorld

Status: a read-only survey of the local sources by a delegated read-only agent (no code changed for it, nothing
run; item 3 was re-checked by hand, items 4-6 are its reading of the code and are not verified on the host). The owner allowed all five
benchmarks to be tried. Conclusion: the pass/fail arm can be wired, the diagnosis arms cannot yet (no verifier
or check adapter for these two domains), and the work does not fit an afternoon. Line numbers are those of
snapshot h.

## Why they are not supported today

`scripts/run_fivebench_g_stage.py` restricts learning to the API-only domains (`API_ONLY`, `TRAIN` has no entry
for the two), `skillopt/active_evidence/profiles.py` marks both `supported: False`, and the evaluation backends
that do support them (`skillopt/continual_eval/backends.py`) were only driven by the older study F pipeline.

## Required changes for the pass/fail arm (minimal set)

1. Tool: admit both benchmarks in `prepare_active_evidence` and in the `--benchmark` choices; add `TRAIN` specs
   (each task is its own family: at most 79 / 38 step families so that a non-empty pool remains).
2. Profiles / protocol: allow both for the `scalar` feedback arm only.
3. `stage.py`: the default rubric record is built for every arm (`default_policy_record`), but only three
   benchmarks have one -- a KeyError after `started.json` is written, leaving an unresumable stage; build it for
   diagnosis arms only.
4. `stage.py` `bind_step_rows`: `row["output"]["output"] == saved["prediction"]["output"]` is false for both
   domains (the adapter returns projected text, the saved output is a structured object) -- the stage would go
   `pending` AFTER the full paid rollout; compare through the same projection.
5. Tool `learn`: enter the native learning environment as study F does (`continual_learning/launch.py`), or every
   ALFWorld episode is rejected although the readiness check passes.
6. SpreadsheetBench runtime: F's recalculation qualification binds absolute paths of F's source tree; a new
   snapshot needs re-qualification and a prepare option that swaps those fields.
7. Tests that pin today's refusals must be updated.

## To be checked on the development machine before any paid run

Sheet re-qualification under the new snapshot path and the pinned images; eight concurrent ALFWorld subprocesses
and LibreOffice containers during learning (F ran learning serially, `solver_workers = 1`); the `ALFWORLD_DATA`
variable in the launching shell; the SpreadsheetBench unknown rate against the 50% known-rows floor; the reserve
arithmetic, which assumes two calls per position while an ALFWorld episode takes up to `max_steps` calls.

## What it would and would not give

Development panels are 80 (SpreadsheetBench) and 39 (ALFWorld) tasks: after a step subset, a reserved pool of
20-40 tasks gives decision rule v2 little power -- though not none: with coverage, replay and adverse completion
satisfied, 5 wins against 0 losses already reach a one-sided p of 0.03125. Whatever the decision rule, development
evidence on these two domains will be imprecise; their test splits are 280 and 134 tasks.
