# Codex review of the v2 stage reads (one round) — 2026-10-23

- Reviewer: codexdl, `-m gpt-6-astra -c model_reasoning_effort="ultra" -s read-only`, on a mirror of the dl dev tree
  without `data/` (brief: BRIEF-stage.md; the reviewed change: stage-reads.diff before these fixes).
- Verdict: **NOT ACCEPTABLE — 4 MAJOR, 0 BLOCKER, 0 MINOR.** Codex reproduced #1, #2 and #4 offline (fake sandbox,
  in-memory consent probe) and reproduced the 608M read / 2,055M solver caps. No pytest, model call or data access.
- Rule: one round per item; all BLOCKER/MAJOR fixed; no second round unless the smoke fails.

| # | Finding (Codex) | Fix | Test |
|---|---|---|---|
| 1 | `evaluation.py` sharing: equal `enabled` does not prove identical requests — F can enable `p`, `p.before_call` times out, the shell drops the notes but keeps `enabled`; a stage holding `p` would share F's faulted outcome. | `_linked` sends a stage cell to the fallback (it runs itself after the blocks) when the source cell recorded any fault; `cells.share_same` refuses a faulted source (second guard). | `test_a_source_cell_that_recorded_a_fault_is_never_shared` (transient `before_call` fault on F's cell: S1 and S3 run themselves, with notes, another request; fallback 2) |
| 2 | `_derived` copies F's predicate faults into a stage route: F's `applies(p)` times out → stage `{p}` empty → shares C without its own routing. | `_derived` returns None when any stage procedure faulted in F's routing of the item; `stage_plan` routes such items (per item) in the stage package's own worker; `derived` = number of items routed from F's. | `test_an_item_where_fs_routing_faulted_is_routed_in_the_stage_packages_own_worker` (F's route faults → F shares C; S1 routed in its own worker enables `p` and runs; S3 shares S1's cell) |
| 3 | Stage metadata only when stage packages exist: rows of C and F alone (step 1 already passed F on, or only the last step accepted) dropped the whole stage table from unseal and report. | The unit record carries `stages` whenever a stage read runs (`plan_sha256` None, empty `derived`/`sources`, `fallback` 0 when no stage arm runs). | `test_a_stage_read_whose_rows_are_c_and_f_alone_records_its_stage_table` (both row shapes; unseal and `stage_table`) |
| 4 | The exported `evaluate(..., stages=...)` accepts stage arms under a v1-only consent (only the CLI path was guarded). | `evaluate`/`_evaluate` take `run_configuration`; with `stages` it must be a stage-read configuration and its exact consent is checked before an attempt opens or a panel is read; `run_unit_spec` passes it. | `test_the_unit_reads_stage_arms_only_under_their_configurations_exact_consent` (no configuration / "main" / v1 consent refused, no attempt dir, panel untouched; main-v2 + stage consent reads) |

Mutation check (scratch copy on dl, `work/mutcheck-stage.py`): each fix reverted on its own → its test fails (5/5
killed). Tests after the fixes: tests/test_execskill_stage_read.py 13 passed; the 18 related files 236 passed; the full
suite 1,469 passed (31 min, 2026-10-23 17:26).
