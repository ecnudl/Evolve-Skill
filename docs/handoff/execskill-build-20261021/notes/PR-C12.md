# PR-C12: ticket C1-2, the SpreadsheetBench no-workbook shortcut probe (fivebench-execskill-v1)

Binding: registration §7.2 (shortcut gate: "表格题去掉工作簿, 2 次都答对的题丢掉; 被丢比例 > 25% 就整套不用"), §9.2
(the shortcut probe is the card arm C, 30 items × 2 runs); plan §1 examiner row, §2.8 (cell record), §3 (hook table,
"Sheet view"); registrar decisions 2026-10-22 row C1-2 ("Implement `solver.solve(..., shortcut="no_workbook")` ... no
preview or sheet content shown; the program still runs on the real input; mode recorded in the cell") and the 13:0x
addendum (pilot-readiness row built now, reviewed in the same single Codex round). Ticket C1-2 (from C1).

Zero model calls, zero network, no git writes. Throwaway mutation copy `/tmp/PR-C12-mut` deleted.

## Files changed (file:line as of 13:0x)

The solver/shell module that builds the view is **`skillopt/execskill/solver.py`** (the copy of the frozen
`backends.solve`, backends.py:397-409; frozen code not edited).

- `skillopt/execskill/solver.py`
  - :27-31 module docstring bullet for the no-workbook mode.
  - :114 `NO_WORKBOOK = "no_workbook"`.
  - :162-171 `_sheet_view(view, runtime, *, shortcut=None)`: the frozen view (same keys, same order, byte for byte)
    unless `shortcut == NO_WORKBOOK`, then the same view without `workbook_preview`; the workbook is not opened for it.
    `routing_view()` (public, used by cells.share_cell, evaluation, s0, smoke, fixtures) keeps the default: unchanged.
  - :221-228 `_Shell.__init__(..., shortcut=None)`: `require` the mode is None or (`NO_WORKBOOK` and the bench is
    SpreadsheetBench), and that the package has no procedure for the bench (`package.for_bench`); :246 kept on the shell.
  - :456-457 shell record: `shortcut` key only when the mode is set (normal shell records unchanged; precedent
    `alfworld_steps`).
  - :551-563 `solve(..., shortcut=None)` documented and handed to `_Shell`.
  - :616-618 `_solve_sheet` docstring; :645 the view of the mode. Routing, notes (none: no procedures), the
    pre-check on `files[0]` and the per-case runs on `public["input_files"]` are unchanged, so the program still runs
    on the real input; the pre-check report stays host-side.
- `skillopt/execskill/cells.py`
  - :35-39 module docstring bullet.
  - :141-142 `_shell`: a cell's `shortcut` (when not None) becomes `solve(..., shortcut=...)`; `_shell` serves both
    the fresh solve and the re-execution replay (`_replay`), so a replay presents the identical no-workbook request.
  - :309-315 `_shortcut(runs)`: the mode the latest shell run's own record states.
  - :329-332 `run_cell` docstring; :403 record: top-level `shortcut` = `_shortcut(runs)`, present only on a cell that
    asked for a mode (normal records unchanged). The request also stays in `record["cell"]["shortcut"]`.
- `skillopt/execskill/examiner.py` (shortcut parts only)
  - :35-39 module docstring (shortcut gate bullet); :57 unused `ConfigurationError` import removed; :73 imports
    `NO_WORKBOOK` from solver (no cycle: nothing solver imports imports examiner; checked by importing examiner, step,
    cells on dl).
  - :86-89 `SHORTCUT_PROBES["spreadsheetbench"] = NO_WORKBOOK`; new `SHORTCUT_MODES = {"spreadsheetbench": NO_WORKBOOK}`.
  - :657-671 `shortcut_variant`: SpreadsheetBench no longer raises `ConfigurationError("spreadsheetbench_no_workbook_
    variant ...")`; its variant keeps the public fields (the real input file), `set` "shortcut", `probe`
    "no_workbook", `variant_of`. OfficeQA/LiveMath unchanged (public-field blanks).
  - :674-681 new `probe_mode(variant)`: the probe cell's `shortcut` key (SpreadsheetBench "no_workbook"; QA None);
    refuses anything that is not a shortcut variant.
  - :732-735 `_mode(cell)`: the record's top-level `shortcut` (what the shell ran in).
  - :738-752 `shortcut()`: every probe cell must have run in its bench's mode (`SHORTCUT_MODES.get(bench)`), else
    ValueError ("Every shortcut-probe cell ran in its bench's probe mode ..."); then the unchanged rule (both runs
    right → dropped; dropped share > `SHORTCUT_DROP_MAX` → set not used). `gates()` unchanged.
- `tests/test_execskill_examiner.py`: `cell()` helper takes `bench`/`shortcut` (kept in `cell` and at the top level
  as run_cell keeps it); T-EXAM-6 now checks the SpreadsheetBench variant (public unchanged, probe, variant_of,
  `probe_mode`), the gate verdict on no-workbook cells (1 of 4 dropped, 25 %, used), and the refusals (SB cell without
  the mode; QA cell with one); the `ConfigurationError` import is gone.
- `tests/test_execskill_shortcut_sb.py` (new, 6 tests):
  1. `..._no_workbook_request_holds_no_workbook_byte_or_preview_text`: byte-level over system+user for both preview
     runtimes (`public-formula-preview-v1`, historical): no zip signature, no zip member name, no base64 of the
     workbook, no `workbook_preview` key, no text of the frozen `_sheet_preview` (raw or JSON-escaped) of either input
     file; positive control: the same check finds every preview text in the normal request; the probe user JSON =
     the normal one minus `workbook_preview` (keys in order), same system prompt, same prediction minus `shell`; the
     same refusals before any call for an invalid preview version or layout.
  2. `..._program_still_runs_on_the_real_input_files`: each per-case run gets the exact bytes of its own input file
     (two cases), the pre-check runs once on the first real input, its report is never in the request.
  3. `..._mode_is_refused_off_spreadsheetbench_with_procedures_and_unknown`: OfficeQA + mode, an unknown mode, and a
     package with a SpreadsheetBench `sheet_feedback` procedure are refused before any call or worker start.
  4. `..._probe_cell_hands_its_mode_to_the_shell_and_its_record_states_it`: through `cells.run_cell` with the card
     arm: `record["cell"]["shortcut"]` and top-level `shortcut` = "no_workbook", both attempts' shell records carry
     it; a timed-out execution re-executes from the stored reply on the same request (no P3, one model call, one
     pre-check); the trajectory has no preview; a plain cell on the same item shows the workbook and has no mode.
  5. `..._shortcut_gate_reaches_its_verdict_on_cells_run_without_the_workbook`: a generated SpreadsheetBench set of 4,
     `probe_items` → `shortcut_variant` → cells → `examiner.shortcut`/`examiner.gates`: 1 of 4 right twice → admitted,
     kept = the other 3; 2 of 4 → `failed == ["shortcut"]`, `dropped_share_above_maximum`; cells run without the mode
     (they saw the workbook) → the gate raises.
  6. `..._mutation_that_shows_the_preview_in_the_probe_is_caught`: in process, (a) a view that ignores the mode →
     the byte check fails; (b) a cell runner that drops the mode → the request leaks, the record's top-level
     `shortcut` is None and the gate refuses.

## Public API

- `solver.NO_WORKBOOK`; `solver.solve(bench, public, card_text, package, call, *, ..., shortcut=None)`.
- Cell dict key `shortcut` (cells.run_cell); record keys `cell.shortcut` (request) and top-level `shortcut` (applied).
- `examiner.SHORTCUT_MODES`, `examiner.probe_mode(variant)`; `examiner.shortcut_variant` accepts SpreadsheetBench.

## Readings and deviations (for the Codex round)

- "No sheet content" = nothing read from the workbook: the preview goes; the task's own public text stays — the
  `instruction` and the `required_answer_position` (which may name a sheet) — exactly as OfficeQA keeps its question.
  `input_path`/`required_output_path` stay (the program must read input.xlsx).
- Only a package without a procedure for SpreadsheetBench may run the mode (ValueError otherwise): procedure hooks can
  read the mounted `/input/input.xlsx` and the pre-check report's `answer_cells`/`message`, so "no sheet content" can
  be guaranteed only on the card arm, which is the registered probe arm (§9.2). Not a registration change.
- The pre-check still runs in the mode (§2.5: every extracted program is pre-checked once); its report is stored,
  never shown. Keeps the mode a pure view change (one container run per probe cell).
- The cell record states the APPLIED mode (from the shell record), not only the request, so a runner that forgets
  the mode cannot pass the gate silently (mutation (b)). The gate raises (ValueError) on a mode mismatch instead of
  recording a verdict: it is wiring breakage, like the gate's other `require`s ("Two runs per shortcut-probe item").
- `cells.py` is outside the files the task named for me; the change is the minimum for "mode recorded in the cell"
  (pass-through in `_shell`, `_shortcut`, one record line). No other agent of this batch claims cells.py.

## Tickets

- `tickets/PR-C12-1.md` → C7e: `step._probe_shortcut` still returns None on SpreadsheetBench; remove that and put
  `examiner.probe_mode(variant)` into the probe cells' `shortcut` key (patch given). Until then the SB gate stays
  `not_run` as before.
- `tickets/PR-C12-2.md` → I1: two mutation-suite entries (sites and expected failures checked on a copy), the stale
  e2e docstring line, the rehearsal/S0 code-map hashes, and the e2e fixture error from PR-C31's canary work.

## Tests (dl, `/data/execskill-dev`, PYTHONDONTWRITEBYTECODE=1 python -B -m pytest -q -p no:cacheprovider)

- `test_execskill_shortcut_sb.py` + `test_execskill_examiner.py`: 14 passed.
- T-SOLVER-1 / equivalence and affected files: `test_execskill_solver.py`, `test_execskill_integration_b2.py`,
  `test_execskill_s0.py`, `test_execskill_cells.py`, `test_execskill_integration_b4.py`, `test_execskill_step.py`:
  87 passed (normal-mode requests byte-identical to the frozen solver).
- Throwaway mutation check (copy of skillopt/scripts/tests under /tmp/PR-C12-mut, deleted): unmutated 6 passed; 6
  mutations (view ignores the mode; runner drops it; record states the request; gate skips the mode; procedures
  allowed; no SB mode) each make every named test fail. The 31 existing mutation-suite sites still occur once each.
- `test_execskill_e2e.py`: 11 errors in the module fixture, raised at e2e.py:453 `evaluation.unseal` →
  `_root_scanned` → `_canary_records` ("No registered test canaries in the run root", evaluation.py:433; that file
  changed 12:55 in PR-C31's C3-1 work). The fixture gets there only after `chain.run` finished both chains (e2e.py:440),
  including OfficeQA step 2, whose admitted generator went through the shortcut probe (real `cells.run_cell` on the
  QA variants, then `examiner.gates` with the new mode check). So the C1-2 change does not break the e2e training path.
  The e2e needs a re-run once C3-1 lands.

## Not done

- step.py wiring (C7e's file; ticket PR-C12-1). No end-to-end step test with a SpreadsheetBench set reaching the
  probe exists until then; test 5 drives the same path without step.py.
- The mutation-suite entries (I1's file; ticket PR-C12-2). The whole suite and smoke rehearsal were not run (rules).
