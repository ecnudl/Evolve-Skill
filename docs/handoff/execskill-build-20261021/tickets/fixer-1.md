# Ticket fixer-1 → registrar / main agent: v1.1 note on the test read (ALFWorld views, scorer artifacts, addendum seal, unseal)

From the fixer (2026-10-22). Isolation review findings 2, 3, 10, 11 and 12; registration §5.3, §8.1; Codex F16, F17.

The fixer changed how the evaluation unit handles test content. The code is in `skillopt/execskill/evaluation.py`.
These changes should be recorded in a registrar v1.1 note, because the registration text does not describe them:

1. **ALFWorld test routing views (finding 2).** A test game's routing view (`ALFWORLD_ROUTING_VIEW`: initial
   observation, admissible commands at reset, task text) is made **in memory inside the evaluation unit**. It comes
   from one reset of the game (`alfworld_reset`, under the episode pool) and is never written to disk. `test_plan`
   refuses a public record that already carries a routing view. Each cell carries its game's room
   (`supply.task_folder`) so that the readout can cluster by room (statistics finding 7).
2. **SpreadsheetBench scorer artifacts (findings 3 and 10).** The frozen v7 scorer's artifact directory is now
   `<attempt>/transient/host_only/scorer_artifacts/<position>`, inside the transient store. That store is deleted on
   every exit (complete, pause, exception), and a `transient-deleted.json` record holds the file count and the
   manifest sha256. The test-side qualification (`shared/test/...`) deletes its own `host_only` tree after
   qualifying and records `scorer-artifacts-deleted.json`; only its sealed qualification record is kept, so the
   recalculated test answer workbooks no longer persist (§8.1 needs this as a registered rule).
3. **Crash leftovers (finding 11).** Before a new attempt starts, every earlier attempt's transient store is deleted
   and recorded (`cleaned_attempts` in `canary_scan.json`). The canary scan then covers the unit root,
   `shared/host_only/diagnostics` and `shared/test`, before the first call and on every exit.
4. **Addendum seal and unseal (finding 12).** The formal-chain addendum is `shared/formal-addendum.md`
   (`protocol.FORMAL_ADDENDUM_DOCUMENT`). `evaluation.seal_addendum(root, evidence=...)` seals it once, as record
   `formal-addendum` {document, sha256, written_at}. The unseal step re-hashes the document against that seal.
   `unseal` now refuses to run until **every** chain directory under the run root has ended (complete or terminated).
   A self-declared addendum JSON is no longer accepted.
5. **ALFWorld room clustering (statistics finding 7).** Every ALFWorld contrast of the readout (Q1, Q3, code vs
   text, τ, placebo) now uses the §6.4 room-cluster paired t (df = rooms - blocks), and the readout records the
   number of rooms. The owner should confirm that the §8.2 bounds are read with this model.

Requests:
- Registrar: write these five points into the v1.1 note (§5.3 test views; §8.1 transient deletion and scan coverage;
  §8.1 / F17 addendum seal and the all-chains-ended rule for unseal; §6.4 / §8.2 room clustering).
- Main agent: give the CLI a `seal-addendum` subcommand that calls `evaluation.seal_addendum`, as an owner action.
  The fixer did not add it, because `scripts/run_execskill.py` still refuses `run`/`terminate` (A13-1).
